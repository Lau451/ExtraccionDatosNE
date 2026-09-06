from typing import Any

from supabase import Client


def buscar_item_proceso(client: Client, *, item_proceso_id: str) -> dict[str, Any] | None:
    """Lectura directa de `items_proceso` -- mismo criterio que
    `services/pcp/gestion/repository.py::buscar_presupuesto` (D1: el acceso a
    la tabla en sí, fuera de un import Python de otro `repository`, no está
    restringido por ese guard)."""
    resultado = (
        client.table("items_proceso")
        .select("id, drogueria_id, proceso_comercial_id, producto_id, descripcion, cantidad")
        .eq("id", item_proceso_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_renglon(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("pcp_renglones").insert(fila).execute().data[0]


def buscar_renglon(client: Client, *, renglon_id: str) -> dict[str, Any] | None:
    resultado = client.table("pcp_renglones").select("*").eq("id", renglon_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def listar_renglones(client: Client, *, pcp_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return (
        client.table("pcp_renglones")
        .select("*")
        .eq("pcp_id", pcp_id)
        .eq("drogueria_id", drogueria_id)
        .order("created_at")
        .execute()
        .data
    )


# -- pcp_renglon_resultados (D4) ----------------------------------------------
#
# 5.4: reutilizada acá como "proveedores seleccionados para negociar" -- una
# fila por proveedor con `resultado='sin_respuesta'` (el estado
# inicial/pendiente que ya define `ck_ppr_resultado_val`, 0011_pcp_modelo.sql
# M4). Ver docstring de `services/pcp/renglones/service.py::seleccionar_proveedores`
# para la justificación completa de no crear una tabla nueva.


def crear_resultados_seleccion(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return client.table("pcp_renglon_resultados").insert(filas).execute().data


def listar_resultados(client: Client, *, pcp_renglon_id: str) -> list[dict[str, Any]]:
    return (
        client.table("pcp_renglon_resultados")
        .select("*")
        .eq("pcp_renglon_id", pcp_renglon_id)
        .execute()
        .data
    )
