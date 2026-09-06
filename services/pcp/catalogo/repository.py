from typing import Any

from supabase import Client


def crear_asociacion(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("producto_proveedores").insert(fila).execute().data[0]


def listar_asociaciones(
    client: Client,
    *,
    producto_id: str,
    drogueria_id: str,
    solo_activos: bool = True,
    es_superadmin: bool = False,
) -> list[dict[str, Any]]:
    # Mismo motivo que gestion/repository.py::listar_pcp (D-PCP-011):
    # superadmin no tiene drogueria_id, eq("drogueria_id", None) rompe con
    # 22P02. RLS ya deja pasar a superadmin sin este filtro de aplicación.
    query = client.table("producto_proveedores").select("*").eq("producto_id", producto_id)
    if not es_superadmin:
        query = query.eq("drogueria_id", drogueria_id)
    if solo_activos:
        query = query.eq("activo", True)
    return query.order("created_at").execute().data
