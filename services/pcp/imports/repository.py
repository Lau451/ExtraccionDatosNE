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


# -- pcp (misma tabla que gestion/repository.py; copia local intencional,
# D1 no prohíbe una copia) ---------------------------------------------------


def crear_pcp(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp").insert(fila).execute().data[0]


def buscar_pcp(client: Client, *, pcp_id: str) -> dict[str, Any] | None:
    resultado = client.table("pcp").select("*").eq("id", pcp_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


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
