from datetime import datetime, timezone
from typing import Any

from supabase import Client


def crear_consulta(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_consultas").insert(fila).execute().data[0]


def marcar_enviada(client: Client, *, consulta_id: str) -> dict[str, Any]:
    """PR11 (tasks.md 11.6) -- transiciona `pcp_consultas.estado` a
    `'enviada'` (ck_pcpc_estado, 0012_pcp_extras.sql M4) y setea
    `fecha_envio`. Solo se llama tras una entrega exitosa por al menos un
    canal -- `service.py::enviar_consulta` nunca la invoca si todos los
    canales intentados fallan (spec "Delivery failure does not corrupt
    grouping": la consulta debe quedar reintentable en `'borrador'`)."""
    return (
        client.table("pcp_consultas")
        .update({"estado": "enviada", "fecha_envio": datetime.now(timezone.utc).isoformat()})
        .eq("id", consulta_id)
        .execute()
        .data[0]
    )


def buscar_consulta(client: Client, *, consulta_id: str) -> dict[str, Any] | None:
    resultado = client.table("pcp_consultas").select("*").eq("id", consulta_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def crear_consulta_renglon(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_consulta_renglones").insert(fila).execute().data[0]


def listar_renglones_consulta(client: Client, *, consulta_id: str) -> list[dict[str, Any]]:
    return (
        client.table("pcp_consulta_renglones")
        .select("*")
        .eq("consulta_id", consulta_id)
        .order("created_at")
        .execute()
        .data
    )


def marcar_resultado_en_consulta(
    client: Client, *, pcp_renglon_id: str, proveedor_id: str, consulta_id: str
) -> dict[str, Any]:
    """Setea `pcp_renglon_resultados.consulta_id` (columna nullable de
    0011_pcp_modelo.sql M4, con la FK hacia `pcp_consultas` agregada recién
    en 0012_pcp_extras.sql M4b una vez que esa tabla existe) para la fila que
    `services/pcp/renglones/service.py::seleccionar_proveedores` (PR5) dejó
    en `sin_respuesta`. Acceso directo a la tabla -- no un import Python de
    `services.pcp.negociacion.repository` -- mismo criterio ya documentado en
    `services/pcp/renglones/repository.py::buscar_item_proceso`: el guard D1
    restringe imports Python entre módulos, nunca el acceso a una tabla en
    sí. Precondición (garantizada por el caller, `service.py::agrupar_renglones`,
    vía `negociacion_service.obtener_resultado`): la fila ya existe para este
    par renglón-proveedor."""
    return (
        client.table("pcp_renglon_resultados")
        .update({"consulta_id": consulta_id})
        .eq("pcp_renglon_id", pcp_renglon_id)
        .eq("proveedor_id", proveedor_id)
        .execute()
        .data[0]
    )
