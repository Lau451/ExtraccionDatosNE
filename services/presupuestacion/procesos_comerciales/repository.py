from typing import Any

from supabase import Client

# Estados que ya no aceptan nuevos documentos/comparativas vinculados -- mismo
# criterio que usaba el legacy services/extraccion/routers/licitaciones.py:listar_activas
# (filtraba fuera de la tabla vieja lo que no estuviera 'abierta'/'en_evaluacion'),
# adaptado al vocabulario de estados de procesos_comerciales.
_ESTADOS_TERMINALES = ("adjudicado", "perdido", "cerrado", "cancelado")


def crear_proceso_comercial(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("procesos_comerciales").insert(fila).execute().data[0]


def listar_procesos_comerciales(
    client: Client, *, drogueria_id: str, activos: bool = True
) -> list[dict[str, Any]]:
    query = (
        client.table("procesos_comerciales")
        .select("id, nombre, clase, estado")
        .eq("drogueria_id", drogueria_id)
        .is_("deleted_at", None)
    )
    if activos:
        query = query.not_.in_("estado", _ESTADOS_TERMINALES)
    return query.order("nombre").execute().data
