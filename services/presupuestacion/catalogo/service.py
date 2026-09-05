from datetime import timedelta
from decimal import Decimal
from typing import Any

from supabase import Client

from services.presupuestacion.catalogo import repository as repo
from services.presupuestacion.catalogo.models import (
    CategoriaCreate,
    CategoriaUpdate,
    CostoCreate,
    ProductoCreate,
    ProductoUpdate,
    ProveedorCreate,
    ProveedorUpdate,
    StockAjuste,
)
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.terceros import api

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
            "laboratorio": body.laboratorio,
            "codigo_anmat": body.codigo_anmat,
            "created_by": usuario_id,
            "updated_by": usuario_id,
        },
    )


def listar_productos(
    client: Client, *, drogueria_id: str, activo: bool | None = None, categoria_id: str | None = None
) -> list[dict[str, Any]]:
    return repo.listar_productos(client, drogueria_id=drogueria_id, activo=activo, categoria_id=categoria_id)


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


# -- proveedores -------------------------------------------------------------------
# Fase 8 (design.md D2/D5): wrapper de compatibilidad sobre
# services.terceros.api -- catalogo/ ya no posee la tabla `proveedores`
# (identidad + rol proveedor viven en services/terceros/identidad/).

_IDENTIDAD_CAMPOS = {
    "razon_social": "razon_social",
    "nombre_comercial": "nombre_fantasia",
    "cuit": "cuit",
}
_ROL_CAMPOS = (
    "tipo",
    "es_competidor",
    "es_proveedor_compra",
    "condicion_pago_id",
    "forma_pago_id",
    "activo",
)


def _combinar_proveedor(tercero: dict[str, Any], rol: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rol["id"],
        "drogueria_id": rol["drogueria_id"],
        "codigo_interno": tercero["codigo_interno"],
        "razon_social": tercero["razon_social"],
        "nombre_comercial": tercero["nombre_fantasia"],
        "cuit": tercero["cuit"],
        "tipo": rol["tipo"],
        "es_competidor": rol["es_competidor"],
        "es_proveedor_compra": rol["es_proveedor_compra"],
        "condicion_pago_id": rol["condicion_pago_id"],
        "forma_pago_id": rol["forma_pago_id"],
        "activo": rol["activo"],
    }


def _combinar_proveedor_embed(fila: dict[str, Any]) -> dict[str, Any]:
    """`fila` viene de api.listar_proveedores_con_tercero/obtener_proveedor_con_tercero:
    la fila de `proveedores` con `terceros` embebido vía PostgREST."""
    return _combinar_proveedor(fila["terceros"], fila)


def crear_proveedor(
    client: Client, *, drogueria_id: str, body: ProveedorCreate, usuario_id: str
) -> dict[str, Any]:
    tercero = api.crear_tercero(
        client,
        drogueria_id=drogueria_id,
        body=api.TerceroCreate(
            razon_social=body.razon_social,
            nombre_fantasia=body.nombre_comercial,
            cuit=body.cuit,
        ),
        usuario_id=usuario_id,
    )
    rol = api.asignar_rol_proveedor(
        client,
        tercero_id=tercero["id"],
        drogueria_id=drogueria_id,
        body=api.ProveedorRolCreate(
            tipo=body.tipo,
            es_competidor=body.es_competidor,
            es_proveedor_compra=body.es_proveedor_compra,
            condicion_pago_id=body.condicion_pago_id,
            forma_pago_id=body.forma_pago_id,
        ),
    )
    return _combinar_proveedor(tercero, rol)


def listar_proveedores(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]:
    filas = api.listar_proveedores_con_tercero(client, drogueria_id=drogueria_id, activo=activo)
    return [_combinar_proveedor_embed(f) for f in filas]


def obtener_proveedor(client: Client, *, proveedor_id: str, drogueria_id: str) -> dict[str, Any]:
    fila = api.obtener_proveedor_con_tercero(client, tercero_id=proveedor_id, drogueria_id=drogueria_id)
    return _combinar_proveedor_embed(fila)


def actualizar_proveedor(
    client: Client, *, proveedor_id: str, drogueria_id: str, body: ProveedorUpdate, usuario_id: str
) -> dict[str, Any]:
    campos = body.model_dump(exclude_unset=True)
    identidad_campos = {v: campos[k] for k, v in _IDENTIDAD_CAMPOS.items() if k in campos}
    rol_campos = {k: campos[k] for k in _ROL_CAMPOS if k in campos}

    if identidad_campos:
        api.actualizar_tercero(
            client,
            tercero_id=proveedor_id,
            drogueria_id=drogueria_id,
            body=api.TerceroUpdate(**identidad_campos),
            usuario_id=usuario_id,
        )
    if rol_campos:
        api.actualizar_rol_proveedor(
            client,
            tercero_id=proveedor_id,
            drogueria_id=drogueria_id,
            body=api.ProveedorRolUpdate(**rol_campos),
        )
    return obtener_proveedor(client, proveedor_id=proveedor_id, drogueria_id=drogueria_id)


def eliminar_proveedor(client: Client, *, proveedor_id: str, drogueria_id: str, usuario_id: str) -> None:
    """D4/D1: desactiva el rol proveedor (activo=false), nunca el tercero --
    el mismo tercero puede seguir activo como cliente. `usuario_id` se
    conserva en la firma por compatibilidad con el router/tests."""
    api.actualizar_rol_proveedor(
        client,
        tercero_id=proveedor_id,
        drogueria_id=drogueria_id,
        body=api.ProveedorRolUpdate(activo=False),
    )


def crear_proveedor_para_endpoint(*, drogueria_id: str, body: ProveedorCreate, usuario_id: str) -> dict[str, Any]:
    return crear_proveedor(get_service_client(), drogueria_id=drogueria_id, body=body, usuario_id=usuario_id)


def actualizar_proveedor_para_endpoint(
    *, proveedor_id: str, drogueria_id: str, body: ProveedorUpdate, usuario_id: str
) -> dict[str, Any]:
    return actualizar_proveedor(
        get_service_client(), proveedor_id=proveedor_id, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id
    )


def eliminar_proveedor_para_endpoint(*, proveedor_id: str, drogueria_id: str, usuario_id: str) -> None:
    eliminar_proveedor(
        get_service_client(), proveedor_id=proveedor_id, drogueria_id=drogueria_id, usuario_id=usuario_id
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
