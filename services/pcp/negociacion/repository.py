from typing import Any

from supabase import Client


def crear_precio_proveedor(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    """Escribe una fila en `precios_proveedor` (D4/D5) -- el primer escritor
    real de esta tabla (`services/presupuestacion/pricing/repository.py` solo
    la lee). `item_proceso_id` siempre viene seteado por el caller (D4:
    "precio puntual", nunca un precio general de producto)."""
    return client.table("precios_proveedor").insert(fila).execute().data[0]


def buscar_resultado(
    client: Client, *, pcp_renglon_id: str, proveedor_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("pcp_renglon_resultados")
        .select("*")
        .eq("pcp_renglon_id", pcp_renglon_id)
        .eq("proveedor_id", proveedor_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def upsert_resultado(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    """Upsert por `uq_ppr_renglon_prov (pcp_renglon_id, proveedor_id)`
    (0011_pcp_modelo.sql M4): actualiza la fila que
    `services/pcp/renglones/service.py::seleccionar_proveedores` (PR5) dejó
    en `resultado='sin_respuesta'` sin crear una segunda fila (la UNIQUE lo
    impediría igual, pero un INSERT crudo fallaría con `23505` en vez de
    transicionar la fila existente). Si por algún motivo no existía una
    selección previa para ese par renglón-proveedor, el mismo upsert la crea
    -- ninguna consulta previa es necesaria."""
    return (
        client.table("pcp_renglon_resultados")
        .upsert(fila, on_conflict="pcp_renglon_id,proveedor_id")
        .execute()
        .data[0]
    )
