from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from supabase import Client

from services.shared.database import get_service_client
from services.shared.exceptions import NotFoundError
from services.productos import repository as repo
from services.productos.models import (
    CaracteristicaCreate,
    CaracteristicaUpdate,
    CategoriaCreate,
    CategoriaUpdate,
    CostoAVersionar,
    EnvaseCreate,
    EnvaseUpdate,
    MarcaCreate,
    MarcaUpdate,
    ProductoCaracteristicaCreate,
)

# -- productos ---------------------------------------------------------------

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


def listar_productos_paginado(
    client: Client,
    *,
    drogueria_id: str,
    activo: bool | None = None,
    categoria_id: str | None = None,
    clasificacion: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    return repo.listar_productos_paginado(
        client,
        drogueria_id=drogueria_id,
        activo=activo,
        categoria_id=categoria_id,
        clasificacion=clasificacion,
        q=q,
        page=page,
        page_size=page_size,
    )


def obtener_producto(client: Client, *, producto_id: str, drogueria_id: str) -> dict[str, Any]:
    producto = repo.obtener_producto(client, producto_id=producto_id)
    if producto is None or producto["drogueria_id"] != drogueria_id:
        raise NotFoundError("No se encontró el producto")
    return producto


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


OrigenCosto = Literal["manual", "import_sistema"]
ResultadoVersionado = Literal["nuevos", "actualizados", "sin_cambios"]


def _versionar_costo(
    client: Client,
    *,
    vigente: dict[str, Any] | None,
    producto_id: str,
    drogueria_id: str,
    costo_unitario: Decimal,
    fecha_desde: date,
    origen: OrigenCosto,
) -> tuple[ResultadoVersionado, dict[str, Any]]:
    """Única regla de versionado de costos (X-ARQ-004): un valor igual conserva el
    vigente; uno distinto lo cierra en `fecha_desde - 1 día` y abre un vigente nuevo."""
    if vigente is not None and Decimal(str(vigente["costo_unitario"])) == costo_unitario:
        return "sin_cambios", vigente

    if vigente is not None:
        fecha_cierre = fecha_desde - timedelta(days=1)
        repo.cerrar_costo_vigente(client, costo_id=vigente["id"], fecha_hasta=fecha_cierre.isoformat())

    nuevo = repo.crear_costo(
        client,
        {
            "producto_id": producto_id,
            "drogueria_id": drogueria_id,
            "costo_unitario": str(costo_unitario),
            "fecha_desde": fecha_desde.isoformat(),
            "fecha_hasta": None,
            "origen": origen,
        },
    )
    return ("nuevos" if vigente is None else "actualizados"), nuevo


def versionar_costos(
    client: Client, *, drogueria_id: str, costos: list[CostoAVersionar], origen: OrigenCosto
) -> dict[str, int]:
    """La misma regla en lote. Los vigentes se leen una vez, antes de escribir."""
    vigentes = repo.costos_vigentes_por_producto(client, producto_ids=[c.producto_id for c in costos])
    conteo = {"nuevos": 0, "actualizados": 0, "sin_cambios": 0}
    for costo in costos:
        resultado, _ = _versionar_costo(
            client,
            vigente=vigentes.get(costo.producto_id),
            producto_id=costo.producto_id,
            drogueria_id=drogueria_id,
            costo_unitario=costo.costo_unitario,
            fecha_desde=costo.fecha_desde,
            origen=origen,
        )
        conteo[resultado] += 1
    return conteo


def listar_costos_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_costos(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id)


# -- stock -----------------------------------------------------------------------

def listar_stock(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    obtener_producto(client, producto_id=producto_id, drogueria_id=drogueria_id)
    return repo.listar_stock(client, producto_id=producto_id)


def listar_stock_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return listar_stock(get_service_client(), producto_id=producto_id, drogueria_id=drogueria_id)
