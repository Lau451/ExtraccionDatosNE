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


# -- terceros legacy (proveedores + clientes, PR5/Fase 9) ------------------------
#
# El esquema plano anterior (upsert directo contra `clientes`/`proveedores` por
# `codigo_interno`) ya no existe: la identidad vive en `terceros` y el import se
# ancla en `terceros_legacy_map` (design.md D1, sección 7). Ambos roles comparten
# esta única implementación, parametrizada por `entidad_legacy`.


def upsert_terceros_legacy(
    client: Client,
    *,
    drogueria_id: str,
    sistema_origen: str,
    entidad_legacy: str,
    filas: list[dict[str, Any]],
    usuario_id: str,
) -> list[dict[str, Any]]:
    """Una sola llamada RPC por lote (design.md sección 7, RPC `upsert_terceros_legacy`
    de la migración 0008): resuelve idempotencia vía `terceros_legacy_map`, vincula
    por CUIT si coincide con un tercero existente, y hace INSERT/UPDATE de
    `terceros` + la tabla de rol dentro de una única transacción por lote.
    Devuelve una fila por elemento de `filas` con `codigo_legacy`, `tercero_id`
    y `accion` ('creado' | 'reusado' | 'vinculado')."""
    resultado = client.rpc(
        "upsert_terceros_legacy",
        {
            "p_drogueria_id": drogueria_id,
            "p_sistema_origen": sistema_origen,
            "p_entidad_legacy": entidad_legacy,
            "p_filas": filas,
            "p_usuario_id": usuario_id,
        },
    ).execute()
    return resultado.data


def codigos_legacy_activos(
    client: Client, *, drogueria_id: str, sistema_origen: str, entidad_legacy: str
) -> dict[str, str]:
    """`codigo_legacy -> tercero_id`, restringido a los terceros cuya fila de ROL
    (clientes o proveedores según `entidad_legacy`) sigue activa. Se usa para
    resolver qué códigos desactivar cuando el último CSV ya no los trae — la
    desactivación por ausencia queda fuera del RPC (design.md sección 7)."""
    tabla_rol = "clientes" if entidad_legacy == "cliente" else "proveedores"
    mapa = (
        client.table("terceros_legacy_map")
        .select("codigo_legacy, tercero_id")
        .eq("drogueria_id", drogueria_id)
        .eq("sistema_origen", sistema_origen)
        .eq("entidad_legacy", entidad_legacy)
        .execute()
        .data
    )
    if not mapa:
        return {}
    tercero_ids = [fila["tercero_id"] for fila in mapa]
    activos = (
        client.table(tabla_rol)
        .select("id")
        .in_("id", tercero_ids)
        .eq("activo", True)
        .execute()
        .data
    )
    ids_activos = {fila["id"] for fila in activos}
    return {
        fila["codigo_legacy"]: fila["tercero_id"]
        for fila in mapa
        if fila["tercero_id"] in ids_activos
    }


def desactivar_rol_por_tercero_ids(
    client: Client, *, entidad_legacy: str, tercero_ids: list[str], usuario_id: str
) -> None:
    """Desactiva solo la fila de ROL (clientes o proveedores), nunca el tercero:
    una empresa que desaparece del CSV de clientes puede seguir activa como
    proveedor (design.md sección 7, D1/D4)."""
    if not tercero_ids:
        return
    tabla_rol = "clientes" if entidad_legacy == "cliente" else "proveedores"
    client.table(tabla_rol).update({"activo": False, "updated_by": usuario_id}).in_(
        "id", tercero_ids
    ).execute()
