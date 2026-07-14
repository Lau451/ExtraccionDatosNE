import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.presupuestacion.compras import repository as repo
from services.presupuestacion.compras.models import (
    CrearOrdenCompraRequest,
    EntregaItemRequest,
    ResultadoEntrega,
    ResultadoOrdenCompra,
)
from services.presupuestacion.core import stock
from services.presupuestacion.core.audit import registrar_cambio, registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError

_DOS_DECIMALES = Decimal("0.01")
_UNIQUE_VIOLATION = "23505"
_ESTADOS_PARA_ENTREGA = ("emitida", "en_entrega", "parcialmente_entregada")


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


def _decimal_o_none(valor: Any) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def _resultado_oc(oc: dict[str, Any]) -> ResultadoOrdenCompra:
    return ResultadoOrdenCompra(
        orden_compra_id=oc["id"],
        numero_oc=oc["numero_oc"],
        estado=oc["estado"],
        monto_total=_decimal_o_none(oc["monto_total"]),
        items_cantidad=oc["items_cantidad"],
    )


def crear_orden_compra(
    client: Client, *, drogueria_id: str, usuario_id: str, body: CrearOrdenCompraRequest
) -> ResultadoOrdenCompra:
    proceso = repo.buscar_proceso_comercial(client, proceso_comercial_id=body.proceso_comercial_id)
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial")
    if proceso["drogueria_id"] != drogueria_id:
        raise ValidationError("El proceso comercial no pertenece a esta droguería")

    monto_total = _q(
        sum((item.cantidad * item.precio_unitario for item in body.items), Decimal("0"))
    )

    fila_oc = {
        "proceso_comercial_id": body.proceso_comercial_id,
        "cliente_id": proceso.get("cliente_id"),
        "drogueria_id": drogueria_id,
        "numero_oc": body.numero_oc,
        "estado": "pendiente",
        "monto_total": str(monto_total),
        "items_cantidad": len(body.items),
        "fecha_emision": body.fecha_emision.isoformat() if body.fecha_emision else None,
        "fecha_entrega_estimada": (
            body.fecha_entrega_estimada.isoformat() if body.fecha_entrega_estimada else None
        ),
        "direccion_entrega": body.direccion_entrega,
        "notas": body.notas,
    }

    try:
        oc = repo.crear_orden_compra(client, fila_oc)
    except APIError as exc:
        if exc.code == _UNIQUE_VIOLATION:
            raise ConflictError(
                f"Ya existe una orden de compra con el número '{body.numero_oc}' — si es una "
                "modificación de una OC existente, hace falta el endpoint de versionado "
                "(todavía no implementado)"
            ) from exc
        raise

    filas_items = [
        {
            "orden_compra_id": oc["id"],
            "drogueria_id": drogueria_id,
            "numero_renglon": item.numero_renglon,
            "descripcion": item.descripcion,
            "cantidad": str(item.cantidad),
            "precio_unitario": str(item.precio_unitario),
            "oferta_item_id": item.oferta_item_id,
            "producto_id": item.producto_id,
        }
        for item in body.items
    ]
    repo.insertar_oc_items(client, filas_items)

    registrar_evento_ciclo_vida(
        client,
        entidad="orden_compra",
        entidad_id=oc["id"],
        drogueria_id=drogueria_id,
        tipo_cambio="creacion",
        origen="usuario",
        usuario_id=usuario_id,
    )

    return _resultado_oc({**oc, "monto_total": str(monto_total), "items_cantidad": len(body.items)})


def confirmar_orden_compra(
    client: Client, *, orden_compra_id: str, usuario_id: str
) -> ResultadoOrdenCompra:
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")
    if oc["estado"] != "pendiente":
        raise ConflictError("Solo se puede confirmar una orden de compra en estado 'pendiente'")

    items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    for item in items:
        oferta_item_id = item.get("oferta_item_id")
        if oferta_item_id is None:
            continue
        oferta = repo.buscar_oferta_item(client, oferta_item_id=oferta_item_id)
        # §5: solo las ofertas PROPIAS ganadoras se marcan adjudicada=TRUE. es_drogueria_propia
        # hoy no se auto-detecta (ver matching de comparativas) así que en la práctica esto no
        # dispara hasta que exista el PATCH manual de asignación — comportamiento esperado.
        if oferta is not None and oferta.get("es_drogueria_propia"):
            repo.marcar_oferta_adjudicada(client, oferta_item_id=oferta_item_id)

    oc_actualizada = repo.actualizar_orden_compra(
        client, orden_compra_id=orden_compra_id, campos={"estado": "emitida"}
    )
    registrar_cambio(
        client,
        entidad="orden_compra",
        entidad_id=orden_compra_id,
        drogueria_id=oc["drogueria_id"],
        campo="estado",
        valor_anterior="pendiente",
        valor_nuevo="emitida",
        origen="usuario",
        usuario_id=usuario_id,
        batch_id=str(uuid.uuid4()),
    )

    return _resultado_oc(oc_actualizada)


def _calcular_estado_entrega(items: list[EntregaItemRequest]) -> str:
    entregados = [item for item in items if item.cantidad_entregada > 0]
    if not entregados:
        return "pendiente"
    if all(item.cantidad_rechazada >= item.cantidad_entregada for item in entregados):
        return "rechazada"
    if any(item.cantidad_rechazada > 0 for item in entregados):
        return "parcial"
    return "entregada"


def _recalcular_estado_orden_compra(client: Client, *, orden_compra_id: str) -> str:
    oc_items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    oc_item_ids = [item["id"] for item in oc_items]
    entrega_items = repo.listar_entrega_items_por_oc_items(client, oc_item_ids=oc_item_ids)

    aceptado_por_item: dict[str, Decimal] = {}
    for entrega_item in entrega_items:
        aceptado = Decimal(str(entrega_item["cantidad_entregada"])) - Decimal(
            str(entrega_item["cantidad_rechazada"])
        )
        oc_item_id = entrega_item["oc_item_id"]
        aceptado_por_item[oc_item_id] = aceptado_por_item.get(oc_item_id, Decimal("0")) + aceptado

    todos_completos = True
    algo_entregado = False
    for item in oc_items:
        aceptado = aceptado_por_item.get(item["id"], Decimal("0"))
        if aceptado > 0:
            algo_entregado = True
        if aceptado < Decimal(str(item["cantidad"])):
            todos_completos = False

    if todos_completos:
        nuevo_estado = "entregada"
    elif algo_entregado:
        nuevo_estado = "parcialmente_entregada"
    else:
        nuevo_estado = "en_entrega"

    repo.actualizar_orden_compra(
        client, orden_compra_id=orden_compra_id, campos={"estado": nuevo_estado}
    )
    return nuevo_estado


def crear_entrega(
    client: Client,
    *,
    orden_compra_id: str,
    items: list[EntregaItemRequest],
    fecha_entrega_planificada: date | None,
    fecha_entrega_real: date | None,
    observaciones: str | None,
) -> ResultadoEntrega:
    """Registra una entrega con las cantidades observadas y, en el mismo paso, libera el
    stock comprometido y descuenta lo aceptado (§6) — no hay un estado "entrega sin
    confirmar" intermedio: una entrega es el registro de algo que ya ocurrió físicamente.

    Nota de alcance: si `stock.entregar_stock_producto` agota reintentos para ALGÚN ítem
    (contención real), la excepción se propaga tal cual y el registro de entrega/items ya
    insertado en este momento queda como está — no se revierte. A diferencia del compromiso
    en presupuestos/ (donde revertir un compromiso fallido es seguro y necesario para no
    sobre-comprometer), acá la entrega ya ocurrió en la realidad; el registro parcial sirve
    de rastro para reconciliar a mano, no hay una versión "deshacer la entrega" razonable.
    """
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    if oc is None:
        raise NotFoundError("No se encontró la orden de compra")
    if oc["estado"] not in _ESTADOS_PARA_ENTREGA:
        raise ConflictError(
            "Solo se puede registrar una entrega para una OC emitida, en entrega o "
            "parcialmente entregada"
        )

    oc_items_por_id = {
        item["id"]: item for item in repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    }
    for item in items:
        if item.oc_item_id not in oc_items_por_id:
            raise NotFoundError(
                f"El ítem {item.oc_item_id} no pertenece a esta orden de compra"
            )

    entregas_previas = repo.listar_entregas_por_orden(client, orden_compra_id=orden_compra_id)
    numero_entrega = len(entregas_previas) + 1
    estado_entrega = _calcular_estado_entrega(items)

    fila_entrega = {
        "orden_compra_id": orden_compra_id,
        "drogueria_id": oc["drogueria_id"],
        "numero_entrega": numero_entrega,
        "fecha_entrega_planificada": (
            fecha_entrega_planificada.isoformat() if fecha_entrega_planificada else None
        ),
        "fecha_entrega_real": (fecha_entrega_real or date.today()).isoformat(),
        "cantidad_items": len(items),
        "estado": estado_entrega,
        "observaciones": observaciones,
    }
    entrega = repo.crear_entrega(client, fila_entrega)

    filas_items = [
        {
            "entrega_oc_id": entrega["id"],
            "drogueria_id": oc["drogueria_id"],
            "oc_item_id": item.oc_item_id,
            "cantidad_entregada": str(item.cantidad_entregada),
            "cantidad_rechazada": str(item.cantidad_rechazada),
            "motivo_rechazo": item.motivo_rechazo,
            "lote": item.lote,
            "vencimiento": item.vencimiento.isoformat() if item.vencimiento else None,
        }
        for item in items
    ]
    repo.insertar_entrega_items(client, filas_items)

    for item in items:
        producto_id = oc_items_por_id[item.oc_item_id].get("producto_id")
        if producto_id is None:
            continue
        stock.entregar_stock_producto(
            client,
            producto_id=producto_id,
            drogueria_id=oc["drogueria_id"],
            cantidad_entregada=item.cantidad_entregada,
            cantidad_rechazada=item.cantidad_rechazada,
        )

    nuevo_estado_oc = _recalcular_estado_orden_compra(client, orden_compra_id=orden_compra_id)

    return ResultadoEntrega(
        entrega_id=entrega["id"], estado=estado_entrega, orden_compra_estado=nuevo_estado_oc
    )


def crear_orden_compra_para_endpoint(
    *, drogueria_id: str, usuario_id: str, body: CrearOrdenCompraRequest
) -> ResultadoOrdenCompra:
    """Corre con service_role: la RLS de ordenes_compra/oc_items no incluye 'superadmin' en
    INSERT — mismo criterio que el resto de los módulos."""
    return crear_orden_compra(
        get_service_client(), drogueria_id=drogueria_id, usuario_id=usuario_id, body=body
    )


def confirmar_orden_compra_para_endpoint(
    *, orden_compra_id: str, usuario_id: str
) -> ResultadoOrdenCompra:
    return confirmar_orden_compra(
        get_service_client(), orden_compra_id=orden_compra_id, usuario_id=usuario_id
    )


def crear_entrega_para_endpoint(
    *,
    orden_compra_id: str,
    items: list[EntregaItemRequest],
    fecha_entrega_planificada: date | None,
    fecha_entrega_real: date | None,
    observaciones: str | None,
) -> ResultadoEntrega:
    """Corre con service_role: además de entregas_oc/entregas_oc_items, libera y descuenta
    stock_productos, cuya RLS de UPDATE solo permite admin/gerencia/compras."""
    return crear_entrega(
        get_service_client(),
        orden_compra_id=orden_compra_id,
        items=items,
        fecha_entrega_planificada=fecha_entrega_planificada,
        fecha_entrega_real=fecha_entrega_real,
        observaciones=observaciones,
    )
