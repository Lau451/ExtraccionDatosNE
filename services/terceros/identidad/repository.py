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


def listar_terceros(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    # Embeds default to LEFT JOIN semantics (unlike the `!inner` embeds below), which is
    # exactly what a listing needs here: a tercero with no role assigned yet must still
    # appear, just with an empty `clientes`/`proveedores` array. The service layer turns
    # those arrays into `tiene_rol_cliente`/`tiene_rol_proveedor` booleans for the list's
    # role badge, without a second round-trip per row.
    query = (
        client.table("terceros")
        .select("*, clientes(id), proveedores(id)")
        .eq("drogueria_id", drogueria_id)
        .is_("deleted_at", None)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("razon_social").execute().data


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
    query = client.table("clientes").select("*, terceros!inner(*)").eq("drogueria_id", drogueria_id)
    if activo is not None:
        query = query.eq("activo", activo).eq("terceros.activo", activo)
    return query.execute().data


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
    query = (
        client.table("proveedores").select("*, terceros!inner(*)").eq("drogueria_id", drogueria_id)
    )
    if activo is not None:
        query = query.eq("activo", activo).eq("terceros.activo", activo)
    return query.execute().data


def buscar_proveedor_con_tercero(client: Client, *, tercero_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("proveedores").select("*, terceros(*)").eq("id", tercero_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None
