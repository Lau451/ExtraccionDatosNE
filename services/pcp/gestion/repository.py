from typing import Any

from supabase import Client


def buscar_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None:
    """Lectura directa de `presupuestos` -- nunca vía
    `services.presupuestacion.presupuestos.repository` (D1: services/pcp/**
    no puede importar el repository de otro módulo; el acceso a la tabla en
    sí, fuera de un import Python, no está restringido por ese guard)."""
    resultado = (
        client.table("presupuestos")
        .select("id, drogueria_id, proceso_comercial_id")
        .eq("id", presupuesto_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_pcp(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp").insert(fila).execute().data[0]


def buscar_pcp(client: Client, *, pcp_id: str) -> dict[str, Any] | None:
    resultado = client.table("pcp").select("*").eq("id", pcp_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def actualizar_pcp(client: Client, *, pcp_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp").update(campos).eq("id", pcp_id).execute().data[0]


def listar_pcp(
    client: Client,
    *,
    drogueria_id: str,
    estado: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[dict[str, Any]]:
    query = client.table("pcp").select("*").eq("drogueria_id", drogueria_id)
    if estado is not None:
        query = query.eq("estado", estado)
    if fecha_desde is not None:
        query = query.gte("fecha_entrega_solicitada", fecha_desde)
    if fecha_hasta is not None:
        query = query.lte("fecha_entrega_solicitada", fecha_hasta)
    return query.order("fecha_entrega_solicitada").execute().data
