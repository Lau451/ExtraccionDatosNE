from typing import Any

from supabase import Client

# Fase 8 (design.md D5): este módulo ya no gestiona la tabla `clientes` ni
# `cliente_contactos` (la primera se lee/escribe vía services.terceros.api;
# la segunda fue eliminada por 0008_terceros_modelo.sql y reemplazada por
# `terceros_contactos`). Lo único que sigue siendo propio de presupuestación
# -- sin equivalente en terceros/ -- es cliente_formato_documentos y
# cliente_observaciones.


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
