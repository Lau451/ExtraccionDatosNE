from datetime import datetime, timezone
from typing import Any

from supabase import Client


def buscar_cliente(client: Client, *, cliente_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("clientes")
        .select("id, drogueria_id")
        .eq("id", cliente_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def obtener_cliente(client: Client, *, cliente_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("clientes")
        .select("*")
        .eq("id", cliente_id)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_clientes(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    query = (
        client.table("clientes")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .is_("deleted_at", None)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("nombre").execute().data


def crear_cliente(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("clientes").insert(fila).execute().data[0]


def actualizar_cliente(client: Client, *, cliente_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("clientes").update(campos).eq("id", cliente_id).execute().data[0]


def soft_delete_cliente(client: Client, *, cliente_id: str, usuario_id: str) -> None:
    client.table("clientes").update(
        {
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": usuario_id,
            "activo": False,
        }
    ).eq("id", cliente_id).execute()


def crear_contacto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("cliente_contactos").insert(fila).execute().data[0]


def listar_contactos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return (
        client.table("cliente_contactos")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("es_principal", desc=True)
        .execute()
        .data
    )


def actualizar_contacto(client: Client, *, contacto_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("cliente_contactos").update(campos).eq("id", contacto_id).execute().data[0]


def buscar_contacto(client: Client, *, contacto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("cliente_contactos").select("*").eq("id", contacto_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_formato_documento(
    client: Client, *, cliente_id: str, doc_type: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("cliente_formato_documentos")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("doc_type", doc_type)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_formato_documento(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("cliente_formato_documentos").insert(fila).execute().data[0]


def actualizar_formato_documento(
    client: Client, *, formato_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("cliente_formato_documentos")
        .update(campos)
        .eq("id", formato_id)
        .execute()
        .data[0]
    )


def listar_formato_documentos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return (
        client.table("cliente_formato_documentos")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("doc_type")
        .execute()
        .data
    )


def crear_observacion(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("cliente_observaciones").insert(fila).execute().data[0]


def listar_observaciones(client: Client, *, cliente_id: str) -> list[dict[str, Any]]:
    return (
        client.table("cliente_observaciones")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )
