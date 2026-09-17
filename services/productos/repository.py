from datetime import datetime, timezone
from typing import Any

from supabase import Client

from services.presupuestacion.imports.service import DEPOSITO_SENTINEL

# -- productos ---------------------------------------------------------------

def crear_producto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("productos").insert(fila).execute().data[0]


# PostgREST/Supabase acota cada respuesta a un máximo de filas (1000 por
# defecto) aunque no se pida .limit() explícito. Sin paginar, un catálogo de
# miles de productos (como el maestro legacy importado) se corta en
# silencio: el frontend nunca ve los productos que caen después del corte,
# y una búsqueda por código puede no encontrar algo que sí existe. Se pagina
# con .range() hasta que una página vuelve incompleta.
_TAMANO_PAGINA_PRODUCTOS = 1000


def listar_productos(
    client: Client,
    *,
    drogueria_id: str,
    activo: bool | None = None,
    categoria_id: str | None = None,
    clasificacion: str | None = None,
    q: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    def _query():
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
        if clasificacion is not None:
            query = query.eq("clasificacion", clasificacion)
        if q:
            # q busca por nombre O codigo_interno — el mismo filtro que el
            # frontend hacía en el navegador contra las 7144 filas.
            patron = q.replace("%", "").replace(",", "")
            query = query.or_(f"nombre.ilike.%{patron}%,codigo_interno.ilike.%{patron}%")
        return query.order("nombre")

    if limit is not None:
        # Camino de búsqueda acotada (pantalla de gestión con buscador): una
        # sola llamada, sin recorrer todo el catálogo.
        return _query().limit(limit).execute().data

    # Camino "traer todo" (ej. selector de producto en PCP): pagina en
    # bloques de 1000 porque PostgREST corta ahí por defecto sin avisar.
    productos: list[dict[str, Any]] = []
    inicio = 0
    while True:
        pagina = _query().range(inicio, inicio + _TAMANO_PAGINA_PRODUCTOS - 1).execute().data
        productos.extend(pagina)
        if len(pagina) < _TAMANO_PAGINA_PRODUCTOS:
            return productos
        inicio += _TAMANO_PAGINA_PRODUCTOS


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


# -- marcas / envases / caracteristicas (catalogos) --------------------------------

def _crear_catalogo(client: Client, *, tabla: str, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table(tabla).insert(fila).execute().data[0]


def _listar_catalogo(
    client: Client, *, tabla: str, drogueria_id: str, activa: bool | None
) -> list[dict[str, Any]]:
    query = client.table(tabla).select("*").eq("drogueria_id", drogueria_id)
    if activa is not None:
        query = query.eq("activa", activa)
    return query.order("nombre").execute().data


def _obtener_catalogo(client: Client, *, tabla: str, item_id: str) -> dict[str, Any] | None:
    resultado = client.table(tabla).select("*").eq("id", item_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def _actualizar_catalogo(client: Client, *, tabla: str, item_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table(tabla).update(campos).eq("id", item_id).execute().data[0]


def crear_marca(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return _crear_catalogo(client, tabla="marcas", fila=fila)


def listar_marcas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return _listar_catalogo(client, tabla="marcas", drogueria_id=drogueria_id, activa=activa)


def obtener_marca(client: Client, *, marca_id: str) -> dict[str, Any] | None:
    return _obtener_catalogo(client, tabla="marcas", item_id=marca_id)


def actualizar_marca(client: Client, *, marca_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return _actualizar_catalogo(client, tabla="marcas", item_id=marca_id, campos=campos)


def crear_envase(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return _crear_catalogo(client, tabla="envases", fila=fila)


def listar_envases(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return _listar_catalogo(client, tabla="envases", drogueria_id=drogueria_id, activa=activa)


def obtener_envase(client: Client, *, envase_id: str) -> dict[str, Any] | None:
    return _obtener_catalogo(client, tabla="envases", item_id=envase_id)


def actualizar_envase(client: Client, *, envase_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return _actualizar_catalogo(client, tabla="envases", item_id=envase_id, campos=campos)


def crear_caracteristica(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return _crear_catalogo(client, tabla="caracteristicas", fila=fila)


def listar_caracteristicas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return _listar_catalogo(client, tabla="caracteristicas", drogueria_id=drogueria_id, activa=activa)


def obtener_caracteristica(client: Client, *, caracteristica_id: str) -> dict[str, Any] | None:
    return _obtener_catalogo(client, tabla="caracteristicas", item_id=caracteristica_id)


def actualizar_caracteristica(client: Client, *, caracteristica_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return _actualizar_catalogo(client, tabla="caracteristicas", item_id=caracteristica_id, campos=campos)


# -- producto_caracteristicas (asignacion N:M) --------------------------------------

def listar_caracteristicas_producto(client: Client, *, producto_id: str) -> list[dict[str, Any]]:
    return (
        client.table("producto_caracteristicas")
        .select("*")
        .eq("producto_id", producto_id)
        .execute()
        .data
    )


def asignar_caracteristica_producto(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("producto_caracteristicas").insert(fila).execute().data[0]


def quitar_caracteristica_producto(client: Client, *, producto_id: str, caracteristica_id: str) -> None:
    (
        client.table("producto_caracteristicas")
        .delete()
        .eq("producto_id", producto_id)
        .eq("caracteristica_id", caracteristica_id)
        .execute()
    )


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
