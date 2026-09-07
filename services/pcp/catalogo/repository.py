from typing import Any

from supabase import Client


def crear_asociacion(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("producto_proveedores").insert(fila).execute().data[0]


def listar_asociaciones(
    client: Client, *, producto_id: str, drogueria_id: str, solo_activos: bool = True
) -> list[dict[str, Any]]:
    query = (
        client.table("producto_proveedores")
        .select("*")
        .eq("producto_id", producto_id)
        .eq("drogueria_id", drogueria_id)
    )
    if solo_activos:
        query = query.eq("activo", True)
    return query.order("created_at").execute().data
