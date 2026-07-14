from typing import Any

from supabase import Client

# -- productos -----------------------------------------------------------

def codigos_existentes_productos(client: Client, *, drogueria_id: str, codigos: list[str]) -> set[str]:
    if not codigos:
        return set()
    resultado = (
        client.table("productos")
        .select("codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .in_("codigo_interno", codigos)
        .execute()
    )
    return {fila["codigo_interno"] for fila in resultado.data}


def codigos_activos_productos(client: Client, *, drogueria_id: str) -> set[str]:
    resultado = (
        client.table("productos")
        .select("codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .execute()
    )
    return {fila["codigo_interno"] for fila in resultado.data}


def insertar_productos(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("productos").insert(filas).execute()


def actualizar_productos_existentes(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("productos").upsert(filas, on_conflict="drogueria_id,codigo_interno").execute()


def desactivar_productos(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None:
    if codigos:
        client.table("productos").update({"activo": False, "updated_by": usuario_id}).eq(
            "drogueria_id", drogueria_id
        ).in_("codigo_interno", codigos).execute()


def mapear_productos_por_codigo(
    client: Client, *, drogueria_id: str, codigos: list[str]
) -> dict[str, str]:
    if not codigos:
        return {}
    resultado = (
        client.table("productos")
        .select("id, codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .in_("codigo_interno", codigos)
        .execute()
    )
    return {fila["codigo_interno"]: fila["id"] for fila in resultado.data}


# -- costos ----------------------------------------------------------------

def costos_vigentes_por_producto(client: Client, *, producto_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not producto_ids:
        return {}
    resultado = (
        client.table("costos_productos")
        .select("id, producto_id, costo_unitario")
        .in_("producto_id", producto_ids)
        .is_("fecha_hasta", None)
        .execute()
    )
    return {fila["producto_id"]: fila for fila in resultado.data}


def crear_costo(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("costos_productos").insert(fila).execute().data[0]


def cerrar_costo_vigente(client: Client, *, costo_id: str, fecha_hasta: str) -> None:
    client.table("costos_productos").update({"fecha_hasta": fecha_hasta}).eq("id", costo_id).execute()


# -- stock -------------------------------------------------------------------

def upsert_stock(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("stock_productos").upsert(filas, on_conflict="producto_id,deposito").execute()


# -- proveedores ---------------------------------------------------------------

def codigos_existentes_proveedores(
    client: Client, *, drogueria_id: str, codigos: list[str]
) -> set[str]:
    if not codigos:
        return set()
    resultado = (
        client.table("proveedores")
        .select("codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .in_("codigo_interno", codigos)
        .execute()
    )
    return {fila["codigo_interno"] for fila in resultado.data}


def codigos_activos_proveedores(client: Client, *, drogueria_id: str) -> set[str]:
    resultado = (
        client.table("proveedores")
        .select("codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .not_.is_("codigo_interno", None)
        .execute()
    )
    return {fila["codigo_interno"] for fila in resultado.data}


def insertar_proveedores(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("proveedores").insert(filas).execute()


def actualizar_proveedores_existentes(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("proveedores").upsert(filas, on_conflict="drogueria_id,codigo_interno").execute()


def desactivar_proveedores(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None:
    if codigos:
        client.table("proveedores").update({"activo": False, "updated_by": usuario_id}).eq(
            "drogueria_id", drogueria_id
        ).in_("codigo_interno", codigos).execute()


# -- clientes --------------------------------------------------------------------

def mapear_clientes_por_codigo(
    client: Client, *, drogueria_id: str, codigos: list[str]
) -> dict[str, str]:
    if not codigos:
        return {}
    resultado = (
        client.table("clientes")
        .select("id, codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .in_("codigo_interno", codigos)
        .execute()
    )
    return {fila["codigo_interno"]: fila["id"] for fila in resultado.data}


def codigos_activos_clientes(client: Client, *, drogueria_id: str) -> set[str]:
    resultado = (
        client.table("clientes")
        .select("codigo_interno")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)
        .is_("deleted_at", None)
        .not_.is_("codigo_interno", None)
        .execute()
    )
    return {fila["codigo_interno"] for fila in resultado.data}


def insertar_clientes(client: Client, filas: list[dict[str, Any]]) -> None:
    if filas:
        client.table("clientes").insert(filas).execute()


def actualizar_cliente(client: Client, *, cliente_id: str, campos: dict[str, Any]) -> None:
    if campos:
        client.table("clientes").update(campos).eq("id", cliente_id).execute()


def desactivar_clientes(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None:
    if codigos:
        client.table("clientes").update({"activo": False, "updated_by": usuario_id}).eq(
            "drogueria_id", drogueria_id
        ).in_("codigo_interno", codigos).execute()
