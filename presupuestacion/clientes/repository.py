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
