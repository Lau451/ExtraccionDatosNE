from typing import Any

from supabase import Client

# design.md D8: idempotencia ancla en pcp_legacy_map, sin discriminador
# entidad_legacy (PCP es una sola entidad, a diferencia de terceros_legacy_map).
SISTEMA_ORIGEN_LEGACY = "legacy"


# -- pcp_legacy_map (idempotencia, D8) --------------------------------------


def buscar_mapa_legacy(client: Client, *, drogueria_id: str, codigo_legacy: str) -> dict[str, Any] | None:
    resultado = (
        client.table("pcp_legacy_map")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .eq("sistema_origen", SISTEMA_ORIGEN_LEGACY)
        .eq("codigo_legacy", codigo_legacy)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_mapa_legacy(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_legacy_map").insert(fila).execute().data[0]


# -- resolución de cliente_id vía terceros.codigo_interno (D8: "ya existente",
# sin tabla ni lógica de resolución nueva) -- lectura directa de las tablas
# `terceros`/`clientes`, no un import Python del `repository` de
# `services/terceros/**` (D1: el acceso a la tabla en sí, fuera de un import
# Python de otro `repository`, no está restringido por ese guard -- mismo
# criterio ya documentado en `gestion/repository.py::buscar_presupuesto` y
# `renglones/repository.py::buscar_item_proceso`). ---------------------------


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


# -- placeholders procesos_comerciales / presupuestos (D8: solo en el primer
# import de un "número de PCP") ----------------------------------------------


def crear_proceso_comercial(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("procesos_comerciales").insert(fila).execute().data[0]


def crear_presupuesto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("presupuestos").insert(fila).execute().data[0]


# -- pcp (misma tabla que gestion/repository.py; copia local intencional,
# D1 no prohíbe una copia -- mismo criterio ya documentado en
# `negociacion/repository.py::buscar_estado_presupuesto`) -------------------


def crear_pcp(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp").insert(fila).execute().data[0]


def buscar_pcp(client: Client, *, pcp_id: str) -> dict[str, Any] | None:
    resultado = client.table("pcp").select("*").eq("id", pcp_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


# -- items_proceso: find-or-create por (proceso_comercial_id, numero_renglon)
# (D8: "items_proceso es find-or-created por renglón, keyed by
# (proceso_comercial_id, numero_renglon)") -----------------------------------


def buscar_item_proceso_por_renglon(
    client: Client, *, proceso_comercial_id: str, numero_renglon: int
) -> dict[str, Any] | None:
    resultado = (
        client.table("items_proceso")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .eq("numero_renglon", numero_renglon)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_item_proceso(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("items_proceso").insert(fila).execute().data[0]


# -- pcp_renglones: find-or-create por (pcp_id, item_proceso_id) -- evita
# duplicar el renglón en un reimport (8.4/8.7a) leyendo antes de escribir, en
# vez de depender de capturar el unique_violation de uq_pcpr_pcp_item. -------


def buscar_renglon_por_item(
    client: Client, *, pcp_id: str, item_proceso_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("pcp_renglones")
        .select("*")
        .eq("pcp_id", pcp_id)
        .eq("item_proceso_id", item_proceso_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_renglon(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_renglones").insert(fila).execute().data[0]


# -- presupuesto_legacy_map (idempotencia del import legado de presupuestos,
# migración 0015) -- mismo esqueleto que pcp_legacy_map, mismo
# SISTEMA_ORIGEN_LEGACY (ver comentario de la migración: "mirror deliberado de
# pcp_legacy_map"). ---------------------------------------------------------


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


# -- presupuestos / presupuesto_items -----------------------------------------
# `crear_presupuesto` ya existe más arriba (placeholder de PCP) -- mismo
# insert genérico, se reusa tal cual acá.


def buscar_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None:
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


def borrar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> None:
    """Segunda mitad de la compensación de `_crear_presupuesto_legacy`: debe
    correr DESPUÉS de `borrar_presupuesto` -- `items_proceso` (fk_ip_proc,
    ON DELETE CASCADE desde procesos_comerciales) queda bloqueado por
    `presupuesto_items.item_proceso_id` (fk_pi_item, sin CASCADE) hasta que
    esa fila ya no exista, mismo orden documentado en
    tests/pcp/imports/test_service.py::_limpiar_import para pcp/presupuestos/
    procesos_comerciales."""
    client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


def crear_presupuesto_item(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("presupuesto_items").insert(fila).execute().data[0]


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
