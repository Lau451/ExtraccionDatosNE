from typing import Any

from supabase import Client


def buscar_extraction_result(client: Client, *, extraction_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("extraction_results").select("*").eq("id", extraction_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("procesos_comerciales")
        .select("id, drogueria_id, cliente_id, clase")
        .eq("id", proceso_comercial_id)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_extracciones(
    client: Client, *, validado: bool | None, limit: int, offset: int
) -> list[dict[str, Any]]:
    # Con validado=False el plan pega contra idx_er_sin_validar (drogueria_id,
    # created_at DESC) WHERE validado = FALSE -- índice parcial ya materializado
    # en ese orden, sin sort extra. RLS (er_sel / mismo_tenant) es la frontera de
    # tenant; no hay filtro manual por drogueria_id acá (§8.1 -- superadmin tiene
    # drogueria_id NULL y quedaría sin resultados si lo agregáramos).
    query = (
        client.table("extraction_results")
        .select(
            "id, document_type, source_filename, row_count, status, validado, "
            "proceso_comercial_id, created_at, procesos_comerciales(nombre)"
        )
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if validado is not None:
        query = query.eq("validado", validado)
    return query.execute().data


def actualizar_extraction_result(
    client: Client, *, extraction_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("extraction_results")
        .update(campos)
        .eq("id", extraction_id)
        .execute()
        .data[0]
    )


def insertar_items_proceso(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("items_proceso").insert(filas).execute().data


def listar_items_proceso_por_proceso(
    client: Client, *, proceso_comercial_id: str
) -> list[dict[str, Any]]:
    return (
        client.table("items_proceso")
        .select("id, numero_renglon")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .execute()
        .data
    )


def buscar_comparativa_vigente(
    client: Client, *, proceso_comercial_id: str
) -> dict[str, Any] | None:
    resultado = (
        client.table("comparativas")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .eq("es_vigente", True)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def invalidar_comparativa(client: Client, *, comparativa_id: str) -> None:
    client.table("comparativas").update({"es_vigente": False}).eq("id", comparativa_id).execute()


def crear_comparativa(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("comparativas").insert(fila).execute().data[0]


def insertar_ofertas_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    return client.table("ofertas_items").insert(filas).execute().data


def actualizar_oferta_item(
    client: Client, *, oferta_item_id: str, campos: dict[str, Any]
) -> None:
    client.table("ofertas_items").update(campos).eq("id", oferta_item_id).execute()


def listar_usuarios_por_rol(
    client: Client,
    *,
    drogueria_id: str,
    roles: tuple[str, ...],
    excluir_id: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        client.table("usuarios")
        .select("id")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)  # no avisar a usuarios desactivados (D6, defecto #3)
        .in_("rol", roles)
    )
    if excluir_id is not None:
        query = query.neq("id", excluir_id)  # no auto-notificar al que validó
    return query.execute().data
