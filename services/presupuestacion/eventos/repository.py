from datetime import datetime, timezone
from typing import Any

from supabase import Client

# -- eventos -----------------------------------------------------------------

def crear_evento(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("eventos").insert(fila).execute().data[0]


def obtener_evento(client: Client, *, evento_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("eventos")
        .select("*")
        .eq("id", evento_id)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_eventos(
    client: Client,
    *,
    drogueria_id: str,
    estado: str | None = None,
    proceso_comercial_id: str | None = None,
    responsable_id: str | None = None,
) -> list[dict[str, Any]]:
    query = client.table("eventos").select("*").eq("drogueria_id", drogueria_id)
    if estado is not None:
        query = query.eq("estado", estado)
    if proceso_comercial_id is not None:
        query = query.eq("proceso_comercial_id", proceso_comercial_id)
    if responsable_id is not None:
        query = query.eq("responsable_id", responsable_id)
    return query.order("fecha_limite").execute().data


def actualizar_evento(client: Client, *, evento_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("eventos").update(campos).eq("id", evento_id).execute().data[0]


def soft_delete_evento(client: Client, *, evento_id: str, usuario_id: str) -> None:
    client.table("eventos").update(
        {"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": usuario_id}
    ).eq("id", evento_id).execute()


def listar_bloqueados_por_dependencia(client: Client, *, depende_de_id: str) -> list[dict[str, Any]]:
    return (
        client.table("eventos")
        .select("id")
        .eq("depende_de_id", depende_de_id)
        .eq("estado", "bloqueado")
        .execute()
        .data
    )


def bloqueo_de_evento(client: Client, *, evento_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("v_eventos_bloqueo").select("*").eq("evento_id", evento_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def calendario(
    client: Client, *, drogueria_id: str, desde: str | None = None, hasta: str | None = None
) -> list[dict[str, Any]]:
    query = client.table("v_calendario").select("*").eq("drogueria_id", drogueria_id)
    if desde is not None:
        query = query.gte("fecha_programada", desde)
    if hasta is not None:
        query = query.lte("fecha_programada", hasta)
    return query.order("fecha_programada").execute().data


# -- eventos_recurrentes ------------------------------------------------------

def crear_evento_recurrente(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("eventos_recurrentes").insert(fila).execute().data[0]


def obtener_evento_recurrente(client: Client, *, evento_recurrente_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("eventos_recurrentes")
        .select("*")
        .eq("id", evento_recurrente_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_eventos_recurrentes(
    client: Client, *, drogueria_id: str, activa: bool | None = None
) -> list[dict[str, Any]]:
    query = client.table("eventos_recurrentes").select("*").eq("drogueria_id", drogueria_id)
    if activa is not None:
        query = query.eq("activa", activa)
    return query.order("titulo").execute().data


def actualizar_evento_recurrente(
    client: Client, *, evento_recurrente_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("eventos_recurrentes")
        .update(campos)
        .eq("id", evento_recurrente_id)
        .execute()
        .data[0]
    )


def listar_recurrentes_a_ejecutar(client: Client) -> list[dict[str, Any]]:
    ahora = datetime.now(timezone.utc).isoformat()
    return (
        client.table("eventos_recurrentes")
        .select("*")
        .eq("activa", True)
        .lte("proxima_ejecucion", ahora)
        .execute()
        .data
    )
