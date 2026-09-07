from datetime import date, timedelta
from typing import Any

from supabase import Client


def listar_pcp_abiertos_por_vencer(client: Client, *, drogueria_id: str, dias: int) -> list[dict[str, Any]]:
    """D12 (design.md): PCPs abiertos (`estado <> 'cerrada'`) cuya
    `fecha_entrega_solicitada` cae entre hoy y los próximos `dias` días --
    la ventana de "PCPs cercanos a su fecha de entrega solicitada" que pide
    la spec `pcp-sugerencias`. `fecha_entrega_solicitada` es nullable
    (0011_pcp_modelo.sql M1): un PCP sin fecha solicitada nunca entra en el
    rango, porque no hay ninguna "proximidad" que evaluar para él."""
    hoy = date.today()
    limite = (hoy + timedelta(days=dias)).isoformat()
    return (
        client.table("pcp")
        .select("id")
        .eq("drogueria_id", drogueria_id)
        .neq("estado", "cerrada")
        .gte("fecha_entrega_solicitada", hoy.isoformat())
        .lte("fecha_entrega_solicitada", limite)
        .execute()
        .data
    )


def listar_renglones_por_producto_en_pcps(
    client: Client, *, drogueria_id: str, producto_id: str, pcp_ids: list[str]
) -> list[dict[str, Any]]:
    """Renglones del producto dado, restringidos al conjunto de PCPs que
    `listar_pcp_abiertos_por_vencer` ya resolvió como "por vencer". `pcp_ids`
    vacío devuelve `[]` sin consultar -- un `in_([])` de postgrest-py arma un
    filtro `in.()` que Postgres rechaza."""
    if not pcp_ids:
        return []
    return (
        client.table("pcp_renglones")
        .select("id, pcp_id, cantidad")
        .eq("drogueria_id", drogueria_id)
        .eq("producto_id", producto_id)
        .in_("pcp_id", pcp_ids)
        .execute()
        .data
    )


def listar_precios_especiales_vigentes_por_producto(
    client: Client, *, drogueria_id: str, producto_id: str
) -> list[dict[str, Any]]:
    """D12: reusa `v_precios_especiales_vigentes` (0012_pcp_extras.sql M6) --
    esa vista ya filtra `activa = true` y `mantenimiento_hasta >=
    CURRENT_DATE`, y ya expone proveedor/banda de cantidad/`dias_restantes`.
    Ese filtrado no se reimplementa acá en Python (D12 lo pide
    explícitamente)."""
    return (
        client.table("v_precios_especiales_vigentes")
        .select(
            "precio_proveedor_id, proveedor, mantenimiento_hasta, dias_restantes, "
            "precio_unitario, cantidad_minima, cantidad_maxima"
        )
        .eq("drogueria_id", drogueria_id)
        .eq("producto_id", producto_id)
        .order("precio_unitario")
        .execute()
        .data
    )
