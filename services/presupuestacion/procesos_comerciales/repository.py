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


def borrar_proceso_comercial_recien_creado(client: Client, *, proceso_comercial_id: str) -> None:
    """Deshace la creación de un proceso que nunca llegó a usarse (compensación
    manual, no hay transacción real vía PostgREST). Borra primero sus filas de
    `historial_cambios` -- el evento 'creacion' que escribió
    `service.crear_proceso_comercial`; fk_hc_proc no tiene CASCADE -- y después el
    proceso, que cascadea `items_proceso` (fk_ip_proc). Ambos borrados filtran por
    este `proceso_comercial_id`, nunca por fecha ni por tipo de evento."""
    client.table("historial_cambios").delete().eq(
        "proceso_comercial_id", proceso_comercial_id
    ).execute()
    client.table("procesos_comerciales").delete().eq("id", proceso_comercial_id).execute()


# -- items_proceso: lecturas para otros módulos (X-ARQ-002,
# odd/tasks/pcp-fachadas.md S3). Las expone `procesos_comerciales/api.py`;
# `services/pcp` las leía antes directo de la tabla. ---------------------------


def buscar_item_proceso(client: Client, *, item_proceso_id: str) -> dict[str, Any] | None:
    resultado = client.table("items_proceso").select("*").eq("id", item_proceso_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def buscar_item_proceso_por_renglon(
    client: Client, *, proceso_comercial_id: str, numero_renglon: int
) -> dict[str, Any] | None:
    resultado = (
        client.table("items_proceso")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .eq("numero_renglon", numero_renglon)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None
