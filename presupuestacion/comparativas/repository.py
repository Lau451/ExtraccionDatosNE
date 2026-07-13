from typing import Any

from supabase import Client


def buscar_oferta_item(client: Client, *, oferta_item_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("ofertas_items").select("*").eq("id", oferta_item_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_proveedor(client: Client, *, proveedor_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("proveedores")
        .select("id, drogueria_id")
        .eq("id", proveedor_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def actualizar_oferta_item(
    client: Client, *, oferta_item_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("ofertas_items")
        .update(campos)
        .eq("id", oferta_item_id)
        .execute()
        .data[0]
    )


def listar_renglones_ganados(client: Client, *, proceso_comercial_id: str) -> list[dict[str, Any]]:
    return (
        client.table("v_renglones_ganados")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .execute()
        .data
    )


def listar_ofertas_sin_matchear(client: Client) -> list[dict[str, Any]]:
    return client.table("v_ofertas_sin_matchear").select("*").execute().data
