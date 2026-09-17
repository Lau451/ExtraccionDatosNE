from datetime import timedelta
from decimal import Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.productos import repository as repo
from services.productos.models import (
    CaracteristicaCreate,
    CaracteristicaUpdate,
    CategoriaCreate,
    CategoriaUpdate,
    CostoCreate,
    EnvaseCreate,
    EnvaseUpdate,
    MarcaCreate,
    MarcaUpdate,
    ProductoCaracteristicaCreate,
    ProductoCreate,
    ProductoUpdate,
    StockAjuste,
)

# -- productos ---------------------------------------------------------------

def crear_producto(
    client: Client, *, drogueria_id: str, body: ProductoCreate, usuario_id: str
) -> dict[str, Any]:
    return repo.crear_producto(
        client,
        {
            "drogueria_id": drogueria_id,
            "codigo_interno": body.codigo_interno,
            "nombre": body.nombre,
            "categoria_id": body.categoria_id,
            "clasificacion": body.clasificacion,
            "droga": body.droga,
            "presentacion": body.presentacion,
            "forma_farmaceutica": body.forma_farmaceutica,
            "marca_id": body.marca_id,
            "envase_id": body.envase_id,
            "alicuota_iva": str(body.alicuota_iva) if body.alicuota_iva is not None else None,
            "codigo_anmat": body.codigo_anmat,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


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
    return repo.listar_productos(
        client,
        drogueria_id=drogueria_id,
        activo=activo,
        categoria_id=categoria_id,
        clasificacion=clasificacion,
        q=q,
        limit=limit,
    )


def obtener_producto(client: Client, *, producto_id: str, drogueria_id: str) -> dict[str, Any]:
    producto = repo.obtener_producto(client, producto_id=producto_id)
    if producto is None or producto["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el producto")
    return producto


def actualizar_producto(
    client: Client, *, producto_id: str, drogueria_id: str, body: ProductoUpdate, usuario_id: str
) -> dict[str, Any]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    campos = body.model_dump(exclude_unset=True)
    if "alicuota_iva" in campos and campos["alicuota_iva"] is not None:
        campos["alicuota_iva"] = str(campos["alicuota_iva"])
    campos["updated_by"] = usuario_id
    return repo.actualizar_producto(client, producto_id=producto_id, campos=campos)


def eliminar_producto(client: Client, *, producto_id: str, drogueria_id: str, usuario_id: str) -> None:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    repo.soft_delete_producto(client, producto_id=producto_id, usuario_id=usuario_id)


def crear_producto_para_endpoint(*, drogueria_id: str, body: ProductoCreate, usuario_id: str) -> dict[str, Any]:
    return crear_producto(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_producto_para_endpoint(
    *, producto_id: str, drogueria_id: str, body: ProductoUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_producto(
        get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def eliminar_producto_para_endpoint(*, producto_id: str, drogueria_id: str, usuario_id: str) -> None:
    eliminar_producto(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id, usuario_id=usuario_id)


# -- categorias ----------------------------------------------------------------

def crear_categoria(client: Client, *, drogueria_id: str, body: CategoriaCreate) -> dict[str, Any]:
    return repo.crear_categoria(
        client, {"drogueria_id": drogueria_id, "nombre": body.nombre, "descripcion": body.descripcion}
    )


def listar_categorias(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar_categorias(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_categoria(
    client: Client, *, categoria_id: str, drogueria_id: str, body: CategoriaUpdate
) -> dict[str, Any]:
    categoria = repo.obtener_categoria(client, categoria_id=categoria_id)
    if categoria is None or categoria["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la categoría")
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_categoria(client, categoria_id=categoria_id, campos=campos)


def crear_categoria_para_endpoint(*, drogueria_id: str, body: CategoriaCreate) -> dict[str, Any]:
    return crear_categoria(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_categoria_para_endpoint(
    *, categoria_id: str, drogueria_id: str, body: CategoriaUpdate
) -> dict[str, Any]:
    return actualizar_categoria(get_service_client(), categoria_id=categoria_id, drogueria_id=drogueria_id, body=body)


# -- marcas / envases / caracteristicas (catalogos) --------------------------------
#
# Mismo shape que categorias (sin descripcion: nombre alcanza para marca,
# envase y caracteristica, a diferencia de categoria que agrupa muchos
# productos y se beneficia de una aclaracion).

def crear_marca(client: Client, *, drogueria_id: str, body: MarcaCreate) -> dict[str, Any]:
    return repo.crear_marca(client, {"drogueria_id": drogueria_id, "nombre": body.nombre})


def listar_marcas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar_marcas(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_marca(client: Client, *, marca_id: str, drogueria_id: str, body: MarcaUpdate) -> dict[str, Any]:
    marca = repo.obtener_marca(client, marca_id=marca_id)
    if marca is None or marca["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la marca")
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_marca(client, marca_id=marca_id, campos=campos)


def crear_marca_para_endpoint(*, drogueria_id: str, body: MarcaCreate) -> dict[str, Any]:
    return crear_marca(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_marca_para_endpoint(*, marca_id: str, drogueria_id: str, body: MarcaUpdate) -> dict[str, Any]:
    return actualizar_marca(get_service_client(), marca_id=marca_id, drogueria_id=drogueria_id, body=body)


def crear_envase(client: Client, *, drogueria_id: str, body: EnvaseCreate) -> dict[str, Any]:
    return repo.crear_envase(client, {"drogueria_id": drogueria_id, "nombre": body.nombre})


def listar_envases(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar_envases(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_envase(client: Client, *, envase_id: str, drogueria_id: str, body: EnvaseUpdate) -> dict[str, Any]:
    envase = repo.obtener_envase(client, envase_id=envase_id)
    if envase is None or envase["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el envase")
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_envase(client, envase_id=envase_id, campos=campos)


def crear_envase_para_endpoint(*, drogueria_id: str, body: EnvaseCreate) -> dict[str, Any]:
    return crear_envase(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_envase_para_endpoint(*, envase_id: str, drogueria_id: str, body: EnvaseUpdate) -> dict[str, Any]:
    return actualizar_envase(get_service_client(), envase_id=envase_id, drogueria_id=drogueria_id, body=body)


def crear_caracteristica(client: Client, *, drogueria_id: str, body: CaracteristicaCreate) -> dict[str, Any]:
    return repo.crear_caracteristica(client, {"drogueria_id": drogueria_id, "nombre": body.nombre})


def listar_caracteristicas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]:
    return repo.listar_caracteristicas(client, drogueria_id=drogueria_id, activa=activa)


def actualizar_caracteristica(
    client: Client, *, caracteristica_id: str, drogueria_id: str, body: CaracteristicaUpdate
) -> dict[str, Any]:
    caracteristica = repo.obtener_caracteristica(client, caracteristica_id=caracteristica_id)
    if caracteristica is None or caracteristica["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró la característica")
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_caracteristica(client, caracteristica_id=caracteristica_id, campos=campos)


def crear_caracteristica_para_endpoint(*, drogueria_id: str, body: CaracteristicaCreate) -> dict[str, Any]:
    return crear_caracteristica(get_service_client(), drogueria_id=drogueria_id, body=body)


def actualizar_caracteristica_para_endpoint(
    *, caracteristica_id: str, drogueria_id: str, body: CaracteristicaUpdate
) -> dict[str, Any]:
    return actualizar_caracteristica(
        get_service_client(), caracteristica_id=caracteristica_id, drogueria_id=drogueria_id, body=body
    )


# -- caracteristicas de producto (asignacion N:M) -----------------------------------

def listar_caracteristicas_producto(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.listar_caracteristicas_producto(client, producto_id=producto_id)


def asignar_caracteristica_producto(
    client: Client,
    *,
    producto_id: str,
    drogueria_id: str,
    body: ProductoCaracteristicaCreate,
    usuario_id: str,
) -> dict[str, Any]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.asignar_caracteristica_producto(
        client,
        {
            "drogueria_id": drogueria_id,
            "producto_id": producto_id,
            "caracteristica_id": body.caracteristica_id,
            "created_by": usuario_id,
        },
    )


def quitar_caracteristica_producto(
    client: Client, *, producto_id: str, caracteristica_id: str, drogueria_id: str
) -> None:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    repo.quitar_caracteristica_producto(client, producto_id=producto_id, caracteristica_id=caracteristica_id)


def listar_caracteristicas_producto_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_caracteristicas_producto(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id)


def asignar_caracteristica_producto_para_endpoint(
    *, producto_id: str, drogueria_id: str, body: ProductoCaracteristicaCreate, usuario_id: str
) -> dict[str, Any]:
    return asignar_caracteristica_producto(
        get_service_client(),
        producto_id=producto_id,
        drogueria_id=drogueria_id,
        body=body,
        usuario_id=usuario_id,
    )


def quitar_caracteristica_producto_para_endpoint(
    *, producto_id: str, caracteristica_id: str, drogueria_id: str
) -> None:
    quitar_caracteristica_producto(
        get_service_client(), producto_id=producto_id, caracteristica_id=caracteristica_id, drogueria_id=drogueria_id
    )


# -- costos ------------------------------------------------------------------------

def listar_costos(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.listar_costos(client, producto_id=producto_id)


def crear_costo(
    client: Client, *, producto_id: str, drogueria_id: str, body: CostoCreate
) -> dict[str, Any]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    vigente = repo.costo_vigente(client, producto_id=producto_id)

    if vigente is not None and Decimal(str(vigente["costo_unitario"])) == body.costo_unitario:
        return vigente

    if vigente is not None:
        fecha_cierre = body.fecha_desde - timedelta(days=1)
        repo.cerrar_costo_vigente(client, costo_id=vigente["id"], fecha_hasta=fecha_cierre.isoformat())

    return repo.crear_costo(
        client,
        {
            "producto_id": producto_id,
            "drogueria_id": drogueria_id,
            "costo_unitario": str(body.costo_unitario),
            "fecha_desde": body.fecha_desde.isoformat(),
            "fecha_hasta": None,
            "origen": "manual",
        },
    )


def listar_costos_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_costos(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id)


def crear_costo_para_endpoint(*, producto_id: str, drogueria_id: str, body: CostoCreate) -> dict[str, Any]:
    return crear_costo(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id, body=body)


# -- stock -----------------------------------------------------------------------

def listar_stock(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.listar_stock(client, producto_id=producto_id)


def ajustar_stock(
    client: Client, *, producto_id: str, drogueria_id: str, body: StockAjuste
) -> dict[str, Any]:
    """Ajuste manual de cantidad_disponible. NO toca cantidad_comprometida —
    esa la mantiene únicamente el motor de compromiso de stock (core/stock.py)."""
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.upsert_stock(
        client,
        {
            "producto_id": producto_id,
            "drogueria_id": drogueria_id,
            "deposito": body.deposito if body.deposito else repo.DEPOSITO_SENTINEL,
            "cantidad_disponible": str(body.cantidad_disponible),
        },
    )


def listar_stock_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_stock(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id)


def ajustar_stock_para_endpoint(*, producto_id: str, drogueria_id: str, body: StockAjuste) -> dict[str, Any]:
    return ajustar_stock(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id, body=body)
