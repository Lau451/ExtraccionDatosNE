# Repository del módulo oc_entregas (T3). A diferencia de oc_presupuesto/
# (que corre enteramente con el USER client porque la RLS de oc_items ya
# alcanza para todo lo que ese módulo escribe), acá TODAS las funciones
# esperan el SERVICE client: `eoc_del`/`eoci_del` (RLS de entregas_oc /
# entregas_oc_items) solo permiten DELETE a es_superadmin(), y reemplazar un
# plan (PUT, D4 "solo mientras esté 'pendiente'") necesita borrar las filas
# del plan anterior -- ninguno de los roles de planificación (admin/gerencia/
# lider_comercial/comercial) podría hacerlo con el user client. Correr TODO
# el módulo (lecturas incluidas) con un único tipo de client evita mezclar dos
# modelos de autorización distintos en el mismo módulo; el aislamiento por
# droguería que la RLS daría gratis se reemplaza acá por un filtro explícito
# `drogueria_id` en cada query, igual que services/presupuestacion/compras/
# repository.py (que tiene el mismo problema con `stock_productos`).
from typing import Any

from supabase import Client

_TAMANO_LOTE = 200


def buscar_orden_compra(client: Client, *, orden_compra_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ordenes_compra")
        .select("id, drogueria_id, cliente_id, numero_oc, cantidad_entregas")
        .eq("id", orden_compra_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_oc_items(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    """Todas las columnas que la planificación necesita del renglón de OC,
    incluidas las de vínculo (para derivar el estado con la MISMA lógica que
    oc_presupuesto.service._derivar_estado, D4) -- ordenados por
    numero_renglon para una respuesta estable."""
    return (
        client.table("oc_items")
        .select(
            "id, orden_compra_id, numero_renglon, numero_renglon_documento, descripcion, "
            "cantidad, producto_id, presupuesto_item_id, vinculo_descartado"
        )
        .eq("orden_compra_id", orden_compra_id)
        .order("numero_renglon")
        .execute()
        .data
    )


def listar_productos_por_ids(client: Client, *, producto_ids: list[str]) -> list[dict[str, Any]]:
    """`nombre` + `unidades_por_presentacion` (0031) para los renglones
    confirmados con producto vinculado. Troceado en lotes de 200, mismo
    criterio que oc_presupuesto/repository.py (`_en_lotes`)."""
    if not producto_ids:
        return []
    ids_unicos = list(dict.fromkeys(producto_ids))
    productos: list[dict[str, Any]] = []
    for inicio in range(0, len(ids_unicos), _TAMANO_LOTE):
        lote = ids_unicos[inicio : inicio + _TAMANO_LOTE]
        resultado = (
            client.table("productos")
            .select("id, nombre, unidades_por_presentacion")
            .in_("id", lote)
            .execute()
        )
        productos.extend(resultado.data)
    return productos


def listar_entregas_oc(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    return (
        client.table("entregas_oc")
        .select("id, numero_entrega, fecha_entrega_planificada, estado")
        .eq("orden_compra_id", orden_compra_id)
        .order("numero_entrega")
        .execute()
        .data
    )


def listar_entregas_oc_items(
    client: Client, *, entrega_oc_ids: list[str]
) -> list[dict[str, Any]]:
    if not entrega_oc_ids:
        return []
    items: list[dict[str, Any]] = []
    for inicio in range(0, len(entrega_oc_ids), _TAMANO_LOTE):
        lote = entrega_oc_ids[inicio : inicio + _TAMANO_LOTE]
        resultado = (
            client.table("entregas_oc_items")
            .select("entrega_oc_id, oc_item_id, cantidad_planificada")
            .in_("entrega_oc_id", lote)
            .execute()
        )
        items.extend(resultado.data)
    return items


def borrar_entregas_oc(client: Client, *, orden_compra_id: str) -> None:
    """Reemplazo de plan (D4, PUT § "solo mientras esté pendiente"): borra
    TODAS las `entregas_oc` de esta OC -- `fk_eoci_ent ... ON DELETE CASCADE`
    (docs/schema/extractor_final.sql) se lleva puestas sus
    `entregas_oc_items` sin necesidad de un segundo delete. El caller ya
    verificó que ninguna esté en un estado distinto de 'pendiente' antes de
    llamar acá (si no, el plan está bloqueado y ni siquiera se llega a este
    punto)."""
    client.table("entregas_oc").delete().eq("orden_compra_id", orden_compra_id).execute()


def actualizar_cantidad_entregas(
    client: Client, *, orden_compra_id: str, cantidad_entregas: int
) -> dict[str, Any]:
    return (
        client.table("ordenes_compra")
        .update({"cantidad_entregas": cantidad_entregas})
        .eq("id", orden_compra_id)
        .execute()
        .data[0]
    )
