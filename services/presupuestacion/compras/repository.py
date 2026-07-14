from typing import Any

from supabase import Client


def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("procesos_comerciales")
        .select("id, drogueria_id, cliente_id")
        .eq("id", proceso_comercial_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_orden_compra(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("ordenes_compra").insert(fila).execute().data[0]


def insertar_oc_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("oc_items").insert(filas).execute().data


def buscar_orden_compra(client: Client, *, orden_compra_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ordenes_compra").select("*").eq("id", orden_compra_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_oc_items(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    return (
        client.table("oc_items")
        .select("*")
        .eq("orden_compra_id", orden_compra_id)
        .execute()
        .data
    )


def actualizar_orden_compra(
    client: Client, *, orden_compra_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("ordenes_compra")
        .update(campos)
        .eq("id", orden_compra_id)
        .execute()
        .data[0]
    )


def buscar_oferta_item(client: Client, *, oferta_item_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ofertas_items").select("*").eq("id", oferta_item_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def marcar_oferta_adjudicada(client: Client, *, oferta_item_id: str) -> None:
    client.table("ofertas_items").update({"adjudicada": True}).eq("id", oferta_item_id).execute()


def crear_entrega(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("entregas_oc").insert(fila).execute().data[0]


def insertar_entrega_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("entregas_oc_items").insert(filas).execute().data


def listar_entregas_por_orden(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]:
    return (
        client.table("entregas_oc")
        .select("*")
        .eq("orden_compra_id", orden_compra_id)
        .execute()
        .data
    )


def listar_entrega_items_por_oc_items(
    client: Client, *, oc_item_ids: list[str]
) -> list[dict[str, Any]]:
    if not oc_item_ids:
        return []
    return (
        client.table("entregas_oc_items")
        .select("*")
        .in_("oc_item_id", oc_item_ids)
        .execute()
        .data
    )
