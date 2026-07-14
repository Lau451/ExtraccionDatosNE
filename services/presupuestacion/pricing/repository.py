from datetime import date
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from supabase import Client


def _primero_en_rango(filas: list[dict[str, Any]], cantidad: Decimal) -> dict[str, Any] | None:
    for fila in filas:
        minima = fila.get("cantidad_minima")
        maxima = fila.get("cantidad_maxima")
        if minima is not None and cantidad < Decimal(str(minima)):
            continue
        if maxima is not None and cantidad > Decimal(str(maxima)):
            continue
        return fila
    return None


def buscar_precio_especial_puntual(
    client: Client, *, item_proceso_id: str, cantidad: Decimal
) -> dict[str, Any] | None:
    hoy = date.today().isoformat()
    resultado = (
        client.table("precios_proveedor")
        .select("*")
        .eq("item_proceso_id", item_proceso_id)
        .eq("activa", True)
        .gte("mantenimiento_hasta", hoy)
        .order("precio_unitario")
        .execute()
    )
    return _primero_en_rango(resultado.data, cantidad)


def buscar_precio_especial_general(
    client: Client, *, producto_id: str, drogueria_id: str, cantidad: Decimal
) -> dict[str, Any] | None:
    hoy = date.today().isoformat()
    resultado = (
        client.table("precios_proveedor")
        .select("*")
        .is_("item_proceso_id", None)
        .eq("producto_id", producto_id)
        .eq("drogueria_id", drogueria_id)
        .eq("activa", True)
        .gte("mantenimiento_hasta", hoy)
        .order("precio_unitario")
        .execute()
    )
    return _primero_en_rango(resultado.data, cantidad)


def buscar_costo_estandar_vigente(client: Client, *, producto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("costos_productos")
        .select("*")
        .eq("producto_id", producto_id)
        .is_("fecha_hasta", None)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def _alcance_or(columna: str, valor: str | None) -> str:
    if valor is None:
        return f"{columna}.is.null"
    return f"{columna}.is.null,{columna}.eq.{valor}"


def buscar_regla_aplicable(
    client: Client,
    *,
    drogueria_id: str,
    cliente_id: str | None,
    clase_proceso: str,
    categoria_id: str | None,
) -> dict[str, Any] | None:
    resultado = (
        client.table("reglas_pricing")
        .select("*")
        .eq("drogueria_id", drogueria_id)
        .eq("activa", True)
        .or_(_alcance_or("cliente_id", cliente_id))
        .or_(_alcance_or("clase_proceso", clase_proceso))
        .or_(_alcance_or("categoria_id", categoria_id))
        .order("prioridad", desc=True)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_precio_mercado(
    client: Client, *, producto_id: str, drogueria_id: str, meses_ventana: int
) -> dict[str, Any] | None:
    desde = (date.today() - relativedelta(months=meses_ventana)).isoformat()
    resultado = (
        client.table("v_precio_mercado_producto")
        .select("*")
        .eq("producto_id", producto_id)
        .eq("drogueria_id", drogueria_id)
        .gte("ultima_muestra", desde)
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_stock_libre(client: Client, *, producto_id: str) -> Decimal:
    resultado = (
        client.table("stock_productos")
        .select("cantidad_disponible, cantidad_comprometida")
        .eq("producto_id", producto_id)
        .execute()
    )
    disponible = sum((Decimal(str(f["cantidad_disponible"])) for f in resultado.data), Decimal("0"))
    comprometida = sum((Decimal(str(f["cantidad_comprometida"])) for f in resultado.data), Decimal("0"))
    return disponible - comprometida


def buscar_producto(client: Client, *, producto_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("productos")
        .select("id, categoria_id, drogueria_id")
        .eq("id", producto_id)
        .limit(1)
        .execute()
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


def buscar_presupuesto_abierto(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("presupuestos")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .in_("estado", ["generado", "en_revision"])
        .limit(1)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def buscar_items_con_producto(client: Client, *, proceso_comercial_id: str) -> list[dict[str, Any]]:
    resultado = (
        client.table("items_proceso")
        .select("*")
        .eq("proceso_comercial_id", proceso_comercial_id)
        .not_.is_("producto_id", None)
        .execute()
    )
    return resultado.data
