from datetime import date
from typing import Any

from supabase import Client

# Debe ser <= `max_rows` de PostgREST: con una página más grande, el tope del servidor
# devolvería una página "corta" y se cortaría la lectura antes de tiempo.
_TAMANO_PAGINA = 500
_ORDEN = ("fecha_entrega_planificada", "orden_compra_id", "numero_entrega", "numero_renglon")


def listar_compromisos(
    client: Client, *, drogueria_id: str, desde: date | None, hasta: date
) -> list[dict[str, Any]]:
    """Lee `v_compromisos_entregas` (security_invoker: aplica la RLS de quien consulta);
    el filtro por `drogueria_id` es explícito igual, como en el resto de los módulos."""
    filas: list[dict[str, Any]] = []
    inicio = 0
    while True:
        # Query nueva por página; orden estable para que las ventanas no se solapen ni salteen.
        consulta = (
            client.table("v_compromisos_entregas")
            .select("*")
            .eq("drogueria_id", drogueria_id)
            .lte("fecha_entrega_planificada", hasta.isoformat())
        )
        if desde is not None:
            consulta = consulta.gte("fecha_entrega_planificada", desde.isoformat())
        for columna in _ORDEN:
            consulta = consulta.order(columna)
        pagina = consulta.range(inicio, inicio + _TAMANO_PAGINA - 1).execute().data
        filas.extend(pagina)
        if len(pagina) < _TAMANO_PAGINA:
            return filas
        inicio += _TAMANO_PAGINA


def proxima_fecha(client: Client, *, drogueria_id: str, despues_de: date) -> date | None:
    """Primera `fecha_entrega_planificada` estrictamente posterior a `despues_de`, o None."""
    filas = (
        client.table("v_compromisos_entregas")
        .select("fecha_entrega_planificada")
        .eq("drogueria_id", drogueria_id)
        .gt("fecha_entrega_planificada", despues_de.isoformat())
        .order("fecha_entrega_planificada")
        .limit(1)
        .execute()
        .data
    )
    return date.fromisoformat(filas[0]["fecha_entrega_planificada"]) if filas else None
