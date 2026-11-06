"""Repositorio del import legado de presupuestos (movido desde
`services/pcp/imports/repository.py`, odd/tasks/procesos-comerciales-dueno.md S1).

`procesos_comerciales` no se escribe acá: el proceso lo crea y lo compensa su
dueño, `services/presupuestacion/procesos_comerciales/service.py`.
"""

from typing import Any

from supabase import Client

# Mismo valor que `pcp_legacy_map` (ver comentario de la migración 0015:
# "mirror deliberado de pcp_legacy_map").
SISTEMA_ORIGEN_LEGACY = "legacy"


# -- resolución de cliente_id vía terceros.codigo_interno -- lectura directa de
# las tablas `terceros`/`clientes`, misma consulta que
# `services/pcp/imports/repository.py` (copia propia: el import de PCP la sigue
# usando). ----------------------------------------------------------------------


def buscar_tercero_por_codigo(
    client: Client, *, drogueria_id: str, codigo_interno: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("terceros")
        .select("id, drogueria_id")
        .eq("drogueria_id", drogueria_id)
        .eq("codigo_interno", codigo_interno)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_rol_cliente(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("clientes").select("id, drogueria_id").eq("id", tercero_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


# -- presupuesto_legacy_map (idempotencia del import, migración 0015) ----------


def buscar_mapa_legacy_presupuesto(
    client: Client, *, drogueria_id: str, codigo_legacy: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("presupuesto_legacy_map")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .eq("sistema_origen", SISTEMA_ORIGEN_LEGACY)
        .eq("codigo_legacy", codigo_legacy)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_mapa_legacy_presupuesto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("presupuesto_legacy_map").insert(fila).execute().data[0]


# -- presupuestos / items_proceso / presupuesto_items ---------------------------


def crear_presupuesto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("presupuestos").insert(fila).execute().data[0]


def buscar_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None:
    """Sin filtro de `deleted_at`, a diferencia de `repository.py::buscar_presupuesto`:
    mismo comportamiento que tenía el import en `services/pcp/imports`."""
    resultado = client.table("presupuestos").select("*").eq("id", presupuesto_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def borrar_presupuesto(client: Client, *, presupuesto_id: str) -> None:
    """Compensación manual (no hay transacción real vía PostgREST, mismo
    criterio que `services/presupuestacion/extraccion/repository.py::
    borrar_orden_compra`): usada por `_crear_presupuesto_legacy` para
    deshacer el insert de `presupuestos` cuando un insert posterior
    (presupuesto_legacy_map/items_proceso/presupuesto_items) falla. Cascadea
    `presupuesto_items` (fk_pi_pre) y `presupuesto_legacy_map`
    (fk_prelm_presupuesto) -- ambos ON DELETE CASCADE."""
    client.table("presupuestos").delete().eq("id", presupuesto_id).execute()


def crear_item_proceso(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("items_proceso").insert(fila).execute().data[0]


def crear_presupuesto_item(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("presupuesto_items").insert(fila).execute().data[0]


def contar_presupuesto_items_sin_producto(client: Client, *, presupuesto_id: str) -> int:
    """T1b(a): métrica de reimport -- debe coincidir con la de primer import
    (renglones cuyo `producto_id` no se resolvió), no con
    `presupuestos.items_sin_precio` (campo distinto -- renglones sin
    `precio_producto` -- que solo coincidía por casualidad en los tests
    originales cuando ninguna fila traía precio ni código de producto).
    Cuenta del lado del servidor (`count="exact"`, `limit(0)`): `len(data)`
    quedaría truncado por el max-rows de PostgREST en presupuestos grandes."""
    resultado = (
        client.table("presupuesto_items")
        .select("id", count="exact")
        .eq("presupuesto_id", presupuesto_id)
        .is_("producto_id", None)
        .limit(0)
        .execute()
    )
    return resultado.count or 0


# -- productos: resolución opcional de producto_id por codigo_interno (nunca
# bloquea la fila si no matchea -- mismo criterio sin filtro de activo/
# deleted_at que services/presupuestacion/imports/repository.py::
# mapear_productos_por_codigo). ------------------------------------------------


def buscar_producto_por_codigo(
    client: Client, *, drogueria_id: str, codigo_interno: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("productos")
        .select("id")
        .eq("drogueria_id", drogueria_id)
        .eq("codigo_interno", codigo_interno)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None
