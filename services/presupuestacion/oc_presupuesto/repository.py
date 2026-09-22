from typing import Any, Iterable, TypeVar

from supabase import Client

# .in_() codifica cada valor en la URL (GET): con muchos ids de golpe la URL
# supera el límite del servidor y PostgREST devuelve 400 Bad Request. Mismo
# criterio y mismo tamaño que services/presupuestacion/imports/repository.py
# (_TAMANO_LOTE), y el mismo motivo que design.md D3 documenta para este
# módulo: los in_() sobre proceso_comercial_id y presupuesto_id se emiten en
# lotes de 200 ids, nunca de una sola vez.
_TAMANO_LOTE = 200

_T = TypeVar("_T")


def _en_lotes(items: list[_T], tamano: int = _TAMANO_LOTE) -> Iterable[list[_T]]:
    for inicio in range(0, len(items), tamano):
        yield items[inicio : inicio + tamano]


def buscar_orden_compra(client: Client, *, orden_compra_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ordenes_compra")
        .select("id, drogueria_id, cliente_id, numero_oc")
        .eq("id", orden_compra_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_oc_items_precios(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    """Solo `id` + `precio_unitario`: es lo único que el ranking necesita
    (D2/D3). `oc_items.precio_unitario` es NOT NULL (a diferencia de
    presupuesto_items.precio_unitario, C4), así que acá no hace falta
    filtrar None."""
    return (
        client.table("oc_items")
        .select("id, precio_unitario")
        .eq("orden_compra_id", orden_compra_id)
        .execute()
        .data
    )


def listar_procesos_comerciales_del_cliente(
    client: Client, *, drogueria_id: str, cliente_id: str
) -> list[dict[str, Any]]:
    """Paso 1 del lookup de dos pasos (C6): `presupuestos` no tiene
    `cliente_id` directo, solo `proceso_comercial_id`; el cliente vive en
    `procesos_comerciales.cliente_id`."""
    return (
        client.table("procesos_comerciales")
        .select("id, nombre")
        .eq("drogueria_id", drogueria_id)
        .eq("cliente_id", cliente_id)
        .execute()
        .data
    )


def listar_presupuestos_de_procesos(
    client: Client, *, proceso_comercial_ids: list[str]
) -> list[dict[str, Any]]:
    """Paso 2 del lookup de dos pasos (C6). Troceado en lotes de 200 (D3)."""
    if not proceso_comercial_ids:
        return []
    presupuestos: list[dict[str, Any]] = []
    for lote in _en_lotes(proceso_comercial_ids):
        resultado = (
            client.table("presupuestos")
            .select("id, proceso_comercial_id, estado, generado_at, cantidad_items")
            .in_("proceso_comercial_id", lote)
            .execute()
        )
        presupuestos.extend(resultado.data)
    return presupuestos


def listar_presupuesto_items_por_precio(
    client: Client, *, presupuesto_ids: list[str], precios: list[str]
) -> list[dict[str, Any]]:
    """El filtro de precio ES el join (D3): `precios` ya viene normalizado a
    escala 2 y serializado con str() por el caller (service._q2). Acotado a
    `excluido = FALSE` (C4) -- un renglón excluido nunca se cotizó al
    cliente, así que no puede ser el origen de un renglón de su OC. Solo
    `presupuesto_ids` se trocea (D3); `precios` es el conjunto de precios
    DISTINTOS de la propia OC, que en la práctica nunca se acerca a 200."""
    if not presupuesto_ids or not precios:
        return []
    items: list[dict[str, Any]] = []
    for lote in _en_lotes(presupuesto_ids):
        resultado = (
            client.table("presupuesto_items")
            .select(
                "id, presupuesto_id, item_proceso_id, producto_id, precio_unitario, "
                "cantidad_ofertada"
            )
            .in_("presupuesto_id", lote)
            .in_("precio_unitario", precios)
            .eq("excluido", False)
            .execute()
        )
        items.extend(resultado.data)
    return items


def buscar_numeros_presupuesto_legacy(
    client_service: Client, *, presupuesto_ids: list[str]
) -> dict[str, str]:
    """D2.1: lookup con el SERVICE client, acotado a los `presupuesto_id` que
    la query anterior YA autorizó (nunca una lectura abierta). La política
    `prelm_sel` de `presupuesto_legacy_map` excluye a `comercial` y
    `lider_comercial` -- justo los roles que más usan esta pantalla -- así
    que el user client nunca vería esta fila. El service client acá no
    amplía el alcance de datos: solo traduce ids que el usuario YA puede
    leer, y el valor traducido (un número de presupuesto) no es sensible.
    Este es el único uso del service client en todo el módulo (D12)."""
    if not presupuesto_ids:
        return {}
    mapa: dict[str, str] = {}
    for lote in _en_lotes(presupuesto_ids):
        resultado = (
            client_service.table("presupuesto_legacy_map")
            .select("presupuesto_id, codigo_legacy")
            .in_("presupuesto_id", lote)
            .execute()
        )
        mapa.update({fila["presupuesto_id"]: fila["codigo_legacy"] for fila in resultado.data})
    return mapa
