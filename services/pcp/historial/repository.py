from typing import Any

from supabase import Client

# -- pcp_historial -------------------------------------------------------------
#
# Solo INSERT y SELECT: no hay `actualizar_*`/`eliminar_*` en este módulo
# porque pcp_historial no tiene políticas RLS de UPDATE/DELETE ni esos GRANTs
# para `authenticated` (0012_pcp_extras.sql M7, design.md D6) -- la capa de
# repositorio refleja esa restricción en vez de exponer una operación que la
# BD igual rechazaría.


def crear_evento(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_historial").insert(fila).execute().data[0]


def listar_eventos(client: Client, *, pcp_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return (
        client.table("pcp_historial")
        .select("*")
        .eq("pcp_id", pcp_id)
        .eq("drogueria_id", drogueria_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )
