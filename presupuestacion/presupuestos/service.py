import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from supabase import Client

from presupuestacion.core.audit import registrar_cambio
from presupuestacion.core.database import get_service_client
from presupuestacion.core.exceptions import ConflictError, NotFoundError, ValidationError
from presupuestacion.core import stock
from presupuestacion.presupuestos import repository as repo
from presupuestacion.presupuestos.models import ResultadoPresupuesto

_DOS_DECIMALES = Decimal("0.01")
_ESTADOS_APROBABLES = ("generado", "en_revision")


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


def _decimal_o_none(valor: Any) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def _es_item_no_resuelto(item: dict[str, Any]) -> bool:
    return item["metodo_precio"] == "sin_precio" and not item["excluido"]


def _resultado(presupuesto: dict[str, Any]) -> ResultadoPresupuesto:
    return ResultadoPresupuesto(
        presupuesto_id=presupuesto["id"],
        estado=presupuesto["estado"],
        monto_total=_decimal_o_none(presupuesto["monto_total"]),
        cantidad_items=presupuesto["cantidad_items"],
        items_sin_precio=presupuesto["items_sin_precio"],
    )


def _recalcular_totales_presupuesto(
    client: Client, *, presupuesto: dict[str, Any], usuario_id: str
) -> dict[str, Any]:
    items = repo.listar_items_presupuesto(client, presupuesto_id=presupuesto["id"])
    activos = [i for i in items if not i["excluido"]]

    monto_total = _q(
        sum(
            (
                Decimal(str(i["precio_unitario"])) * Decimal(str(i["cantidad_ofertada"]))
                for i in activos
                if i["precio_unitario"] is not None and i["cantidad_ofertada"] is not None
            ),
            Decimal("0"),
        )
    )
    items_sin_precio = sum(1 for i in activos if i["metodo_precio"] == "sin_precio")

    monto_anterior = _q(_decimal_o_none(presupuesto["monto_total"]) or Decimal("0"))
    cambios = {}
    if monto_anterior != monto_total:
        cambios["monto_total"] = (monto_anterior, monto_total)
    if presupuesto["items_sin_precio"] != items_sin_precio:
        cambios["items_sin_precio"] = (presupuesto["items_sin_precio"], items_sin_precio)

    if not cambios:
        return presupuesto

    presupuesto_actualizado = repo.actualizar_presupuesto(
        client,
        presupuesto_id=presupuesto["id"],
        campos={"monto_total": str(monto_total), "items_sin_precio": items_sin_precio},
    )
    batch_id = str(uuid.uuid4())
    for campo, (anterior, nuevo) in cambios.items():
        registrar_cambio(
            client,
            entidad="presupuesto",
            entidad_id=presupuesto["id"],
            drogueria_id=presupuesto["drogueria_id"],
            campo=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo,
            origen="usuario",
            usuario_id=usuario_id,
            batch_id=batch_id,
        )
    return presupuesto_actualizado


def aprobar_presupuesto(
    client: Client, *, presupuesto_id: str, usuario_id: str
) -> ResultadoPresupuesto:
    presupuesto = repo.buscar_presupuesto(client, presupuesto_id=presupuesto_id)
    if presupuesto is None:
        raise NotFoundError("No se encontró el presupuesto")
    if presupuesto["estado"] not in _ESTADOS_APROBABLES:
        raise ConflictError(
            "Solo se puede aprobar un presupuesto en estado 'generado' o 'en_revision'"
        )

    items = repo.listar_items_presupuesto(client, presupuesto_id=presupuesto_id)
    no_resueltos = [i for i in items if _es_item_no_resuelto(i)]
    if no_resueltos:
        raise ValidationError(
            f"Hay {len(no_resueltos)} ítem(s) sin precio sin resolver "
            "(excluir el renglón o fijar un precio manual)"
        )

    ahora = datetime.now(timezone.utc).isoformat()
    presupuesto_actualizado = repo.actualizar_presupuesto(
        client,
        presupuesto_id=presupuesto_id,
        campos={"estado": "aprobado", "aprobado_por": usuario_id, "aprobado_at": ahora},
    )
    registrar_cambio(
        client,
        entidad="presupuesto",
        entidad_id=presupuesto_id,
        drogueria_id=presupuesto["drogueria_id"],
        campo="estado",
        valor_anterior=presupuesto["estado"],
        valor_nuevo="aprobado",
        origen="usuario",
        usuario_id=usuario_id,
        batch_id=str(uuid.uuid4()),
    )
    return _resultado(presupuesto_actualizado)


def ajustar_item(
    client: Client,
    *,
    presupuesto_item_id: str,
    precio_unitario: Decimal | None,
    cantidad_ofertada: Decimal | None,
    excluido: bool | None,
    motivo_exclusion: str | None,
    usuario_id: str,
) -> dict[str, Any]:
    item = repo.buscar_presupuesto_item(client, presupuesto_item_id=presupuesto_item_id)
    if item is None:
        raise NotFoundError("No se encontró el ítem del presupuesto")

    campos: dict[str, Any] = {}
    if precio_unitario is not None:
        if item["precio_original_motor"] is None:
            campos["precio_original_motor"] = item["precio_unitario"]
        campos["precio_unitario"] = str(precio_unitario)
        campos["precio_ajustado_por"] = usuario_id
        campos["metodo_precio"] = "manual"

        costo_usado = _decimal_o_none(item["costo_usado"])
        if costo_usado is not None and costo_usado > 0:
            campos["margen_resultante_pct"] = str(_q((precio_unitario - costo_usado) / costo_usado * 100))
        else:
            campos["margen_resultante_pct"] = None

    if cantidad_ofertada is not None:
        campos["cantidad_ofertada"] = str(cantidad_ofertada)

    if excluido is not None:
        campos["excluido"] = excluido
        campos["motivo_exclusion"] = motivo_exclusion

    if not campos:
        raise ValidationError("No se especificó ningún campo para ajustar")

    item_actualizado = repo.actualizar_presupuesto_item(
        client, presupuesto_item_id=presupuesto_item_id, campos=campos
    )

    presupuesto = repo.buscar_presupuesto(client, presupuesto_id=item["presupuesto_id"])
    if presupuesto is not None:
        _recalcular_totales_presupuesto(client, presupuesto=presupuesto, usuario_id=usuario_id)

    return item_actualizado


def presentar_presupuesto(
    client: Client, *, presupuesto_id: str, usuario_id: str
) -> ResultadoPresupuesto:
    presupuesto = repo.buscar_presupuesto(client, presupuesto_id=presupuesto_id)
    if presupuesto is None:
        raise NotFoundError("No se encontró el presupuesto")
    if presupuesto["estado"] != "aprobado":
        raise ConflictError("Solo se puede presentar un presupuesto en estado 'aprobado'")

    proceso = repo.buscar_proceso_comercial(
        client, proceso_comercial_id=presupuesto["proceso_comercial_id"]
    )
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial")

    if proceso["clase"] == "cotizacion":
        items = repo.listar_items_presupuesto(client, presupuesto_id=presupuesto_id)
        items_a_comprometer = [
            i
            for i in items
            if not i["excluido"] and i["producto_id"] is not None and i["cantidad_ofertada"] is not None
        ]

        compromisos_totales: list[tuple[str, Decimal]] = []
        try:
            for item in items_a_comprometer:
                compromisos = stock.comprometer_stock_producto(
                    client,
                    producto_id=item["producto_id"],
                    drogueria_id=item["drogueria_id"],
                    cantidad=Decimal(str(item["cantidad_ofertada"])),
                )
                compromisos_totales.extend(compromisos)
        except ConflictError as motivo_original:
            # comprometer_stock_producto ya revirtió (o reportó) lo suyo antes de propagar
            # esta excepción -- acá solo falta revertir los ítems anteriores que sí habían
            # comprometido con éxito. Si ESA reversión también falla, liberar_o_reportar
            # encadena el motivo original en vez de dejar que un error de limpieza lo tape.
            stock.liberar_o_reportar(client, compromisos_totales, motivo_original)
            raise

    ahora = datetime.now(timezone.utc).isoformat()
    presupuesto_actualizado = repo.actualizar_presupuesto(
        client,
        presupuesto_id=presupuesto_id,
        campos={"estado": "presentado", "presentado_por": usuario_id, "presentado_at": ahora},
    )
    registrar_cambio(
        client,
        entidad="presupuesto",
        entidad_id=presupuesto_id,
        drogueria_id=presupuesto["drogueria_id"],
        campo="estado",
        valor_anterior=presupuesto["estado"],
        valor_nuevo="presentado",
        origen="usuario",
        usuario_id=usuario_id,
        batch_id=str(uuid.uuid4()),
    )
    repo.actualizar_proceso_comercial(
        client, proceso_comercial_id=proceso["id"], campos={"estado": "presentado"}
    )

    return _resultado(presupuesto_actualizado)


def aprobar_presupuesto_para_endpoint(*, presupuesto_id: str, usuario_id: str) -> ResultadoPresupuesto:
    """Corre con service_role: la RLS de presupuestos no incluye 'superadmin' en UPDATE —
    mismo criterio que pricing/matching, el router nunca importa el service client."""
    return aprobar_presupuesto(get_service_client(), presupuesto_id=presupuesto_id, usuario_id=usuario_id)


def ajustar_item_para_endpoint(
    *,
    presupuesto_item_id: str,
    precio_unitario: Decimal | None,
    cantidad_ofertada: Decimal | None,
    excluido: bool | None,
    motivo_exclusion: str | None,
    usuario_id: str,
) -> dict[str, Any]:
    return ajustar_item(
        get_service_client(),
        presupuesto_item_id=presupuesto_item_id,
        precio_unitario=precio_unitario,
        cantidad_ofertada=cantidad_ofertada,
        excluido=excluido,
        motivo_exclusion=motivo_exclusion,
        usuario_id=usuario_id,
    )


def presentar_presupuesto_para_endpoint(
    *, presupuesto_id: str, usuario_id: str
) -> ResultadoPresupuesto:
    """Corre con service_role: además de presupuestos/presupuesto_items, comprometer stock
    escribe stock_productos, cuya RLS solo permite admin/gerencia/compras en UPDATE — ningún
    rol comercial (ni superadmin) podría comprometer stock vía user_client."""
    return presentar_presupuesto(get_service_client(), presupuesto_id=presupuesto_id, usuario_id=usuario_id)
