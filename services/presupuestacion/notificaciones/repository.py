from datetime import datetime, timezone
from typing import Any

from supabase import Client


def crear_notificacion(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("notificaciones").insert(fila).execute().data[0]


def crear_entrega(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("notificacion_entregas").insert(fila).execute().data[0]


def preferencias_de_tipo(client: Client, *, usuario_id: str, tipo: str) -> list[dict[str, Any]]:
    return (
        client.table("notificacion_preferencias")
        .select("*")
        .eq("usuario_id", usuario_id)
        .eq("tipo", tipo)
        .execute()
        .data
    )


def obtener_notificacion(client: Client, *, notificacion_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("notificaciones").select("*").eq("id", notificacion_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_no_leidas(client: Client, *, destinatario_id: str) -> list[dict[str, Any]]:
    return (
        client.table("notificaciones")
        .select("*")
        .eq("destinatario_id", destinatario_id)
        .is_("leida_at", None)
        .is_("archivada_at", None)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def marcar_leida(client: Client, *, notificacion_id: str) -> dict[str, Any]:
    return (
        client.table("notificaciones")
        .update({"leida_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", notificacion_id)
        .execute()
        .data[0]
    )


def marcar_archivada(client: Client, *, notificacion_id: str) -> dict[str, Any]:
    return (
        client.table("notificaciones")
        .update({"archivada_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", notificacion_id)
        .execute()
        .data[0]
    )


def upsert_preferencia(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return (
        client.table("notificacion_preferencias")
        .upsert(fila, on_conflict="usuario_id,tipo,canal")
        .execute()
        .data[0]
    )


def listar_preferencias(client: Client, *, usuario_id: str) -> list[dict[str, Any]]:
    return (
        client.table("notificacion_preferencias")
        .select("*")
        .eq("usuario_id", usuario_id)
        .execute()
        .data
    )
