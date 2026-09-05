from datetime import datetime, timezone
from typing import Any

from supabase import Client

from services.presupuestacion.imports.service import DEPOSITO_SENTINEL

# -- productos ---------------------------------------------------------------

def crear_producto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("productos").insert(fila).execute().data[0]


def listar_productos(
    client: Client, *, drogueria_id: str, activo: bool | None = None, categoria_id: str | None = None
) -> list[dict[str, Any]]:
    query = (
        client.table("productos")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .is_("deleted_at", None)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    if categoria_id is not None:
        query = query.eq("categoria_id", categoria_id)
    return query.order("nombre").execute().data


def obtener_producto(client: Client, *, producto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("productos")
        .select("*")
        .eq("id", producto_id)
        .is_("deleted_at", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def actualizar_producto(client: Client, *, producto_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("productos").update(campos).eq("id", producto_id).execute().data[0]


def soft_delete_producto(client: Client, *, producto_id: str, usuario_id: str) -> None:
    client.table("productos").update(
        {
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": usuario_id,
            "activo": False,
        }
    ).eq("id", producto_id).execute()


# -- categorias ----------------------------------------------------------------

def crear_categoria(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("categorias").insert(fila).execute().data[0]


def listar_categorias(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    query = client.table("categorias").select("*").eq("drogueria_id", drogueria_id)
    if activa is not None:
        query = query.eq("activa", activa)
    return query.order("nombre").execute().data


def obtener_categoria(client: Client, *, categoria_id: str) -> dict[str, Any] | None:
    resultado = client.table("categorias").select("*").eq("id", categoria_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def actualizar_categoria(client: Client, *, categoria_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("categorias").update(campos).eq("id", categoria_id).execute().data[0]


# -- proveedores -----------------------------------------------------------------
# Fase 8 (design.md D2/D5): `catalogo/` ya no posee la tabla `proveedores`.
# El wrapper de compatibilidad en catalogo/service.py llama a
# services.terceros.api en su lugar -- ver ese módulo.


# -- costos ----------------------------------------------------------------------

def listar_costos(client: Client, *, producto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("costos_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .order("fecha_desde", desc=True)
        .execute()
        .data
    )


def costo_vigente(client: Client, *, producto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("costos_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .is_("fecha_hasta", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def crear_costo(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("costos_productos").insert(fila).execute().data[0]


def cerrar_costo_vigente(client: Client, *, costo_id: str, fecha_hasta: str) -> None:
    client.table("costos_productos").update({"fecha_hasta": fecha_hasta}).eq("id", costo_id).execute()


# -- stock -------------------------------------------------------------------------

def listar_stock(client: Client, *, producto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .order("deposito")
        .execute()
        .data
    )


def buscar_stock_por_deposito(
    client: Client, *, producto_id: str, deposito: str | None
) -> dict[str, Any] | None:
    valor = deposito if deposito else DEPOSITO_SENTINEL
    resultado = (
        client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .eq("deposito", valor)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def upsert_stock(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return (
        client.table("stock_productos")
        .upsert(fila, on_conflict="producto_id,deposito")
        .execute()
        .data[0]
    )
