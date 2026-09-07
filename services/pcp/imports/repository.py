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
