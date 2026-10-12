# Repository del módulo oc_resumen (T1). Lecturas puras con el SERVICE client,
# igual que oc_entregas: el aislamiento por droguería lo da el filtro explícito
# `drogueria_id` en el service. Las lecturas de renglones / entregas se reusan
# de oc_entregas.repository; acá solo van las que cambian de columnas.
from typing import Any

from supabase import Client

from services.presupuestacion.oc_entregas.repository import (  # noqa: F401  (reexport)
    listar_entregas_oc,
    listar_entregas_oc_items,
)

_TAMANO_LOTE = 200


def buscar_orden_compra(client: Client, *, orden_compra_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ordenes_compra")
        .select(
            "id, drogueria_id, cliente_id, numero_oc, fecha_emision, fecha_entrega_estimada, "
            "direccion_entrega, notas, estado, version_numero, monto_total, "
            "exportado_at, exportado_por, archivo_exportado, "
            # Hint obligatorio: ordenes_compra tiene otras FK hacia `usuarios` y sin él
            # PostgREST rechaza el embed por ambiguo (PGRST201). La clave sigue siendo `usuarios`.
            "usuarios!fk_oc_exportadopor(nombre, apellido), "
            "clientes(terceros(razon_social, cuit))"
        )
        .eq("id", orden_compra_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_oc_items(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    return (
        client.table("oc_items")
        .select(
            "id, numero_renglon, numero_renglon_documento, descripcion, cantidad, "
            "precio_unitario, monto_total, producto_id, presupuesto_item_id, vinculo_descartado"
        )
        .eq("orden_compra_id", orden_compra_id)
        .order("numero_renglon")
        .execute()
        .data
    )


def listar_productos_por_ids(client: Client, *, producto_ids: list[str]) -> list[dict[str, Any]]:
    """`codigo_interno` + `nombre` de los productos vinculados, en lotes de 200."""
    if not producto_ids:
        return []
    ids_unicos = list(dict.fromkeys(producto_ids))
    productos: list[dict[str, Any]] = []
    for inicio in range(0, len(ids_unicos), _TAMANO_LOTE):
        lote = ids_unicos[inicio : inicio + _TAMANO_LOTE]
        resultado = (
            client.table("productos").select("id, codigo_interno, nombre").in_("id", lote).execute()
        )
        productos.extend(resultado.data)
    return productos
