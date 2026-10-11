from datetime import date
from typing import Any

from supabase import Client


def listar_compromisos(
    client: Client, *, drogueria_id: str, desde: date | None, hasta: date
) -> list[dict[str, Any]]:
    """Lee `v_compromisos_entregas` (security_invoker: aplica la RLS de quien consulta);
    el filtro por `drogueria_id` es explícito igual, como en el resto de los módulos."""
    consulta = (
        client.table("v_compromisos_entregas")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .lte("fecha_entrega_planificada", hasta.isoformat())
    )
    if desde is not None:
        consulta = consulta.gte("fecha_entrega_planificada", desde.isoformat())
    return consulta.execute().data
