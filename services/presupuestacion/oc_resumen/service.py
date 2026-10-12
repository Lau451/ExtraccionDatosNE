# Servicio del módulo oc_resumen (odd/tasks/oc-resumen.md, T1): resumen de solo
# lectura de una OC. No escribe nada.
from typing import Any

from supabase import Client

from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.oc_entregas.models import (
    EntregaItemPlanOut,
    EntregaPlanOut,
    armar_exportacion,
)
from services.presupuestacion.oc_presupuesto.service import derivar_estado_vinculo
from services.presupuestacion.oc_resumen import repository as repo
from services.presupuestacion.oc_resumen.models import (
    ClienteResumen,
    OcResumenOut,
    ProductoResumen,
    RenglonResumen,
)


def _armar_cliente(oc: dict[str, Any]) -> ClienteResumen | None:
    """Cliente desde el embed `clientes(terceros(...))`; None si la OC no tiene cliente_id."""
    tercero = (oc.get("clientes") or {}).get("terceros")
    if not oc.get("cliente_id") or not tercero:
        return None
    return ClienteResumen(razon_social=tercero["razon_social"], cuit=tercero.get("cuit"))


def _armar_entregas(client: Client, *, orden_compra_id: str) -> list[EntregaPlanOut]:
    entregas = repo.listar_entregas_oc(client, orden_compra_id=orden_compra_id)
    items = repo.listar_entregas_oc_items(client, entrega_oc_ids=[e["id"] for e in entregas])
    items_por_entrega: dict[str, list[EntregaItemPlanOut]] = {}
    for item in items:
        items_por_entrega.setdefault(item["entrega_oc_id"], []).append(
            EntregaItemPlanOut(
                oc_item_id=item["oc_item_id"], cantidad_planificada=item["cantidad_planificada"]
            )
        )
    return [
        EntregaPlanOut(
            numero_entrega=e["numero_entrega"],
            fecha_entrega_planificada=e["fecha_entrega_planificada"],
            estado=e["estado"],
            items=items_por_entrega.get(e["id"], []),
        )
        for e in entregas
    ]


def obtener_resumen(client: Client, *, orden_compra_id: str, drogueria_id: str) -> OcResumenOut:
    oc = repo.buscar_orden_compra(client, orden_compra_id=orden_compra_id)
    # Misma respuesta para "no existe" y "es de otra droguería": no confirma existencia.
    if oc is None or oc["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la orden de compra")

    oc_items = repo.listar_oc_items(client, orden_compra_id=orden_compra_id)
    productos = {
        p["id"]: p
        for p in repo.listar_productos_por_ids(
            client, producto_ids=[i["producto_id"] for i in oc_items if i.get("producto_id")]
        )
    }

    renglones = []
    for item in oc_items:
        producto = productos.get(item.get("producto_id"))
        renglones.append(
            RenglonResumen(
                oc_item_id=item["id"],
                numero_renglon=item["numero_renglon"],
                numero_renglon_documento=item.get("numero_renglon_documento"),
                descripcion=item["descripcion"],
                producto=(
                    ProductoResumen(codigo_interno=producto.get("codigo_interno"), nombre=producto["nombre"])
                    if producto
                    else None
                ),
                cantidad=item["cantidad"],
                precio_unitario=item.get("precio_unitario"),
                monto_total=item.get("monto_total"),
                estado_vinculo=derivar_estado_vinculo(
                    item.get("presupuesto_item_id"), bool(item.get("vinculo_descartado"))
                ),
            )
        )

    return OcResumenOut(
        orden_compra_id=oc["id"],
        numero_oc=oc["numero_oc"],
        cliente=_armar_cliente(oc),
        fecha_emision=oc.get("fecha_emision"),
        fecha_entrega_estimada=oc.get("fecha_entrega_estimada"),
        direccion_entrega=oc.get("direccion_entrega"),
        notas=oc.get("notas"),
        estado=oc["estado"],
        version_numero=oc.get("version_numero"),
        monto_total=oc.get("monto_total"),
        exportacion=armar_exportacion(oc),
        renglones=renglones,
        entregas=_armar_entregas(client, orden_compra_id=orden_compra_id),
    )
