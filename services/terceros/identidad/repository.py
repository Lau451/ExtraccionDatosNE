from typing import Any

from supabase import Client


def buscar_tercero(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("terceros")
        .select("*")
        .eq("id", tercero_id)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


# PostgREST corta a esta cantidad de filas por página si no se pide `.range()`
# explícito. Sin el loop de abajo, una droguería con más terceros que esto pierde
# en silencio todo lo que ordena alfabéticamente después del límite.
_TAMANO_PAGINA = 1000


def _sanitizar_termino_or(q: str) -> str:
    # `,` y `()` son separadores/agrupadores en la sintaxis de filtro PostgREST
    # (`.or_()`); un término de búsqueda con esos caracteres rompería el filtro
    # en vez de buscarse literalmente, así que se descartan.
    return q.translate(str.maketrans({",": " ", "(": " ", ")": " "})).strip()


def listar_terceros(
    client: Client, *, drogueria_id: str, activo: bool | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    # Embeds default to LEFT JOIN semantics (unlike the `!inner` embeds below), which is
    # exactly what a listing needs here: a tercero with no role assigned yet must still
    # appear, just with an empty `clientes`/`proveedores` array. The service layer turns
    # those arrays into `tiene_rol_cliente`/`tiene_rol_proveedor` booleans for the list's
    # role badge, without a second round-trip per row.
    termino = _sanitizar_termino_or(q) if q else None
    filas: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = (
            client.table("terceros")
            .select("*, clientes(id), proveedores(id)")
            .eq("drogueria_id", drogueria_id)
            .is_("deleted_at", None)
        )
        if activo is not None:
            query = query.eq("activo", activo)
        if termino:
            query = query.or_(
                f"razon_social.ilike.%{termino}%,"
                f"cuit.ilike.%{termino}%,"
                f"codigo_interno.ilike.%{termino}%"
            )
        pagina = (
            query.order("razon_social")
            .range(offset, offset + _TAMANO_PAGINA - 1)
            .execute()
            .data
        )
        filas.extend(pagina)
        if len(pagina) < _TAMANO_PAGINA:
            break
        offset += _TAMANO_PAGINA
    return filas


def listar_terceros_paginado(
    client: Client,
    *,
    drogueria_id: str,
    activo: bool | None = None,
    q: str | None = None,
    filtro_rol: str = "todos",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    # Fix de paginación real + filtro de rol server-side (D, odd/tasks/
    # terceros-listado-paginacion-y-rol.md). Antes esta función no existía: el
    # listado paginado armaba TODO en Python sobre `listar_terceros` (loop de
    # a 1000 + slice), y el filtro de rol también se aplicaba en Python porque
    # la semántica vieja de `_coincide_filtro_rol` era excluyente ("cliente Y
    # NO proveedor") -- eso sí requiere un anti-join ("no existe" sobre un
    # embed) que ni PostgREST ni postgrest-py exponen como filtro simple.
    #
    # Al arreglar ese bug de exclusividad (service.py: ahora "clientes"/
    # "proveedores" son chequeos de presencia, sin el "AND NOT"), el filtro de
    # rol pasó a ser expresable 100% server-side: un tercero "tiene" el rol si
    # el embed devuelve al menos una fila, y eso es exactamente lo que hace un
    # embed `!inner` de PostgREST (fuerza INNER JOIN, así que solo matchean
    # filas con al menos una fila relacionada). Confirmado leyendo el código
    # instalado de postgrest-py 2.30.0: `!inner` es sintaxis PostgREST cruda
    # que se pasa tal cual dentro del string de `.select()` -- no depende de
    # ningún método nuevo de la librería, así que no hacía falta "una forma
    # especial" de expresarlo, solo dejar de necesitar la negación.
    termino = _sanitizar_termino_or(q) if q else None
    embed_clientes = "clientes!inner(id)" if filtro_rol in ("clientes", "ambos") else "clientes(id)"
    embed_proveedores = (
        "proveedores!inner(id)" if filtro_rol in ("proveedores", "ambos") else "proveedores(id)"
    )
    query = (
        client.table("terceros")
        .select(f"*, {embed_clientes}, {embed_proveedores}", count="exact")
        .eq("drogueria_id", drogueria_id)
        .is_("deleted_at", None)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    if termino:
        query = query.or_(
            f"razon_social.ilike.%{termino}%,"
            f"cuit.ilike.%{termino}%,"
            f"codigo_interno.ilike.%{termino}%"
        )
    inicio = (page - 1) * page_size
    resultado = query.order("razon_social").range(inicio, inicio + page_size - 1).execute()
    return resultado.data, resultado.count or 0


def crear_tercero(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("terceros").insert(fila).execute().data[0]


def actualizar_tercero(client: Client, *, tercero_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("terceros").update(campos).eq("id", tercero_id).execute().data[0]


# -- rol cliente --------------------------------------------------------------


def buscar_rol_cliente(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = client.table("clientes").select("*").eq("id", tercero_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def crear_rol_cliente(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("clientes").insert(fila).execute().data[0]


def actualizar_rol_cliente(client: Client, *, tercero_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("clientes").update(campos).eq("id", tercero_id).execute().data[0]


# -- rol cliente + tercero combinados (Fase 8: consumidos por
# services/presupuestacion/clientes/, que ya no lee la tabla `clientes`
# directamente — ver D5 en design.md) -------------------------------------


def listar_clientes_con_tercero(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    # `terceros!inner(*)` turns the embed into an INNER JOIN (PostgREST default embed
    # semantics are LEFT JOIN, which would keep the `clientes` row with a null `terceros`
    # payload instead of excluding it). This lets `.eq("terceros.activo", ...)` actually
    # exclude the row when the tercero itself is inactive, not just null out its embed —
    # closing the post-verify gap where a deactivated tercero (activo=false) still
    # appeared in this listing because only `clientes.activo` (the role's own column)
    # was ever filtered.
    filas: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = (
            client.table("clientes")
            .select("*, terceros!inner(*)")
            .eq("drogueria_id", drogueria_id)
        )
        if activo is not None:
            query = query.eq("activo", activo).eq("terceros.activo", activo)
        pagina = query.range(offset, offset + _TAMANO_PAGINA - 1).execute().data
        filas.extend(pagina)
        if len(pagina) < _TAMANO_PAGINA:
            break
        offset += _TAMANO_PAGINA
    return filas


def buscar_cliente_con_tercero(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("clientes").select("*, terceros(*)").eq("id", tercero_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


# -- rol proveedor --------------------------------------------------------------


def buscar_rol_proveedor(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = client.table("proveedores").select("*").eq("id", tercero_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def crear_rol_proveedor(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("proveedores").insert(fila).execute().data[0]


def actualizar_rol_proveedor(client: Client, *, tercero_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("proveedores").update(campos).eq("id", tercero_id).execute().data[0]


# -- rol proveedor + tercero combinados (consumidos por services.terceros.api,
# mismo criterio que listar_clientes_con_tercero) --


def listar_proveedores_con_tercero(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    # Same `!inner` embed rationale as listar_clientes_con_tercero above.
    filas: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = (
            client.table("proveedores")
            .select("*, terceros!inner(*)")
            .eq("drogueria_id", drogueria_id)
        )
        if activo is not None:
            query = query.eq("activo", activo).eq("terceros.activo", activo)
        pagina = query.range(offset, offset + _TAMANO_PAGINA - 1).execute().data
        filas.extend(pagina)
        if len(pagina) < _TAMANO_PAGINA:
            break
        offset += _TAMANO_PAGINA
    return filas


def buscar_proveedor_con_tercero(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("proveedores").select("*, terceros(*)").eq("id", tercero_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None
