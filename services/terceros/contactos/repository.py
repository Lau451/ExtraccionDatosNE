from typing import Any

from supabase import Client


def crear_contacto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("terceros_contactos").insert(fila).execute().data[0]


def buscar_contacto(client: Client, *, contacto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("terceros_contactos").select("*").eq("id", contacto_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_principal_activo(
    client: Client, *, tercero_id: str, excluir_id: str | None = None
) -> dict[str, Any] | None:
    query = (
        client.table("terceros_contactos")
        .select("*")
        .eq("tercero_id", tercero_id)
        .eq("es_principal", True)
        .eq("activo", True)
    )
    if excluir_id is not None:
        query = query.neq("id", excluir_id)
    resultado = query.limit(1).execute()
    return resultado.data[0] if resultado.data else None


def listar_contactos(
    client: Client, *, tercero_id: str, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    query = (
        client.table("terceros_contactos")
        .select("*")
        .eq("tercero_id", tercero_id)
        .eq("drogueria_id", drogueria_id)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("created_at").execute().data


def actualizar_contacto(
    client: Client, *, contacto_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("terceros_contactos").update(campos).eq("id", contacto_id).execute().data[0]
    )
