from typing import Any

from supabase import Client


def buscar_extraction_result(client: Client, *, extraction_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("extraction_results").select("*").eq("id", extraction_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("procesos_comerciales")
        .select("id, drogueria_id, cliente_id, clase")
        .eq("id", proceso_comercial_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def actualizar_extraction_result(
    client: Client, *, extraction_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("extraction_results")
        .update(campos)
        .eq("id", extraction_id)
        .execute()
        .data[0]
    )


def insertar_items_proceso(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("items_proceso").insert(filas).execute().data


def listar_items_proceso_por_proceso(
    client: Client, *, proceso_comercial_id: str
) -> list[dict[str, Any]]:
    return (
        client.table("items_proceso")
        .select("id, numero_renglon")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .execute()
        .data
    )


def buscar_comparativa_vigente(
    client: Client, *, proceso_comercial_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("comparativas")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .eq("es_vigente", True)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def invalidar_comparativa(client: Client, *, comparativa_id: str) -> None:
    client.table("comparativas").update({"es_vigente": False}).eq("id", comparativa_id).execute()


def crear_comparativa(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("comparativas").insert(fila).execute().data[0]


def insertar_ofertas_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("ofertas_items").insert(filas).execute().data


def actualizar_oferta_item(
    client: Client, *, oferta_item_id: str, campos: dict[str, Any]
) -> None:
    client.table("ofertas_items").update(campos).eq("id", oferta_item_id).execute()


def listar_usuarios_por_rol(
    client: Client, *, drogueria_id: str, roles: tuple[str, ...]
) -> list[dict[str, Any]]:
    return (
        client.table("usuarios")
        .select("id")
        .eq("drogueria_id", drogueria_id)
        .in_("rol", roles)
        .execute()
        .data
    )


def crear_notificacion(client: Client, fila: dict[str, Any]) -> None:
    client.table("notificaciones").insert(fila).execute()
