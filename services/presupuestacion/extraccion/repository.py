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


# -- resolución de cliente (D3/D3.1) -- lectura/escritura directa de
# oc_cliente_alias (tabla propia de extraccion/, ver nota de frontera de
# design.md) y de terceros/clientes (D1: acceso directo a la tabla permitido,
# solo se prohíbe importar el repository de otro módulo -- mismo precedente
# que pcp/imports/repository.py::buscar_tercero_por_codigo). ---------------


def buscar_alias_cliente(
    client: Client, *, drogueria_id: str, texto_normalizado: str
) -> dict[str, Any] | None:
    """Nivel 1 de D3 -- match exacto por el índice único uq_oca. Trae embebidos
    los datos del cliente (y del tercero que comparte su id) para que el
    service pueda armar el CandidatoCliente en un solo viaje."""
    resultado = (
        client.table("oc_cliente_alias")
        .select(
            "id, cliente_id, veces_confirmado, "
            "clientes(id, tipo, activo, terceros(razon_social, codigo_interno, cuit, cuit_no_exclusivo))"
        )
        .eq("drogueria_id", drogueria_id)
        .eq("texto_extraido_normalizado", texto_normalizado)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def upsert_alias_cliente(
    client: Client,
    *,
    drogueria_id: str,
    texto_normalizado: str,
    texto_original: str,
    cliente_id: str,
    usuario_id: str | None,
) -> dict[str, Any]:
    """UPSERT sobre uq_oca (drogueria_id, texto_extraido_normalizado) -- D3.1.
    La última confirmación gana: si ya existía un alias con el MISMO
    cliente_id, incrementa veces_confirmado (reconfirmación); si el cliente
    difiere (corrección), resetea a 1 -- un alias corregido es un alias nuevo y
    no hereda la confianza del mapeo equivocado. No es un UPSERT atómico de una
    sola sentencia SQL (PostgREST no expone `ON CONFLICT DO UPDATE SET x =
    CASE...`): lee el estado previo primero y decide en Python, mismo criterio
    que el resto de este repository."""
    existente = buscar_alias_cliente(
        client, drogueria_id=drogueria_id, texto_normalizado=texto_normalizado
    )
    if existente is not None and existente["cliente_id"] == cliente_id:
        veces_confirmado = existente["veces_confirmado"] + 1
    else:
        veces_confirmado = 1

    fila: dict[str, Any] = {
        "drogueria_id": drogueria_id,
        "texto_extraido_normalizado": texto_normalizado,
        "texto_extraido_original": texto_original,
        "cliente_id": cliente_id,
        "veces_confirmado": veces_confirmado,
        "updated_by": usuario_id,
    }
    if existente is None:
        fila["created_by"] = usuario_id

    return (
        client.table("oc_cliente_alias")
        .upsert(fila, on_conflict="drogueria_id,texto_extraido_normalizado")
        .execute()
        .data[0]
    )


def buscar_clientes_por_cuit(
    client: Client, *, drogueria_id: str, cuit_normalizado: str
) -> list[dict[str, Any]]:
    """Nivel 2 de D3 -- terceros ⋈ clientes por CUIT. Embed LEFT (default de
    PostgREST): un tercero con ese CUIT pero sin fila de rol en `clientes`
    vuelve con `clientes=None`, y es el service quien decide omitirlo y
    agregar la advertencia (no es candidato porque no es cliente)."""
    resultado = (
        client.table("terceros")
        .select(
            "id, razon_social, codigo_interno, cuit, cuit_no_exclusivo, "
            "clientes(id, tipo, activo)"
        )
        .eq("drogueria_id", drogueria_id)
        .eq("cuit", cuit_normalizado)
        .is_("deleted_at", None)
        .execute()
    )
    return resultado.data


# -- agrupación multi-archivo (D13/D13.1) -- lectura/escritura directa de
# extraction_results.grupo_id, mismo criterio de acceso directo del resto de
# este repository. ------------------------------------------------------


def listar_miembros_de_grupo(client: Client, *, grupo_id: str) -> list[dict[str, Any]]:
    """Miembros de un grupo de extracciones OC, en el mismo orden en que
    `_leer_filas_grupo` concatena sus filas: `created_at ASC, id ASC`
    (determinista, sin columna extra -- D13 § Lectura del grupo)."""
    return (
        client.table("extraction_results")
        .select(
            "id, source_filename, csv_disk_path, drogueria_id, document_type, "
            "validado, grupo_id, created_at"
        )
        .eq("grupo_id", grupo_id)
        .order("created_at")
        .order("id")
        .execute()
        .data
    )


def actualizar_grupo_id(
    client: Client, *, extraction_id: str, grupo_id: str | None
) -> dict[str, Any]:
    """Setea (camino b, agrupar) o limpia (desagrupar) grupo_id en una sola
    fila de extraction_results."""
    return (
        client.table("extraction_results")
        .update({"grupo_id": grupo_id})
        .eq("id", extraction_id)
        .execute()
        .data[0]
    )


def marcar_validadas(
    client: Client, *, extraction_ids: list[str], usuario_id: str, validado_at: str
) -> None:
    """Bulk sobre el grupo (D13.1 § Confirmación) -- usada por
    `_materializar_orden_compra` (Phase 5) para marcar TODOS los miembros de
    un grupo como validado=true con el mismo validado_por/validado_at, no
    solo el que el usuario abrió."""
    if not extraction_ids:
        return
    client.table("extraction_results").update(
        {"validado": True, "validado_por": usuario_id, "validado_at": validado_at}
    ).in_("id", extraction_ids).execute()


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
