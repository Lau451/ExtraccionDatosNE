from fastapi import APIRouter, Depends, Query
from supabase import Client

from services.shared.auth import UsuarioPerfil, require_capacidad
from services.shared.database import get_user_client
from services.productos.models import (
    CaracteristicaCreate,
    CaracteristicaOut,
    CaracteristicaUpdate,
    CategoriaCreate,
    CategoriaOut,
    CategoriaUpdate,
    CostoOut,
    EnvaseCreate,
    EnvaseOut,
    EnvaseUpdate,
    MarcaCreate,
    MarcaOut,
    MarcaUpdate,
    ProductoCaracteristicaCreate,
    ProductoCaracteristicaOut,
    ProductoListOut,
    ProductoOut,
    StockOut,
)
from services.productos.service import (
    actualizar_caracteristica_para_endpoint,
    actualizar_categoria_para_endpoint,
    actualizar_envase_para_endpoint,
    actualizar_marca_para_endpoint,
    asignar_caracteristica_producto_para_endpoint,
    crear_caracteristica_para_endpoint,
    crear_categoria_para_endpoint,
    crear_envase_para_endpoint,
    crear_marca_para_endpoint,
    listar_caracteristicas,
    listar_caracteristicas_producto_para_endpoint,
    listar_categorias,
    listar_costos_para_endpoint,
    listar_envases,
    listar_marcas,
    listar_productos_paginado,
    listar_stock_para_endpoint,
    obtener_producto,
    quitar_caracteristica_producto_para_endpoint,
)

router = APIRouter()


# -- productos ---------------------------------------------------------------

@router.get("/productos", response_model=ProductoListOut)
def listar_productos_endpoint(
    activo: bool | None = None,
    categoria_id: str | None = None,
    clasificacion: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    # Tope alto a propósito: el selector de producto de PCP necesita "todos
    # los que matchean" en un solo request (~7144 hoy en Nueva Era), no una
    # página de búsqueda -- mismo criterio que el picker de proveedores de
    # terceros.
    page_size: int = Query(50, ge=1, le=10000),
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> ProductoListOut:
    items, total = listar_productos_paginado(
        user_client,
        drogueria_id=usuario.drogueria_id,
        activo=activo,
        categoria_id=categoria_id,
        clasificacion=clasificacion,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ProductoListOut(items=items, total=total)


@router.get("/productos/{producto_id}", response_model=ProductoOut)
def obtener_producto_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> ProductoOut:
    return obtener_producto(user_client, producto_id=producto_id, drogueria_id=usuario.drogueria_id)


# -- categorias ----------------------------------------------------------------

@router.get("/categorias", response_model=list[CategoriaOut])
def listar_categorias_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> list[CategoriaOut]:
    return listar_categorias(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/categorias", response_model=CategoriaOut)
def crear_categoria_endpoint(
    body: CategoriaCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> CategoriaOut:
    return crear_categoria_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.patch("/categorias/{categoria_id}", response_model=CategoriaOut)
def actualizar_categoria_endpoint(
    categoria_id: str,
    body: CategoriaUpdate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> CategoriaOut:
    return actualizar_categoria_para_endpoint(
        categoria_id=categoria_id, drogueria_id=usuario.drogueria_id, body=body
    )


# -- marcas ----------------------------------------------------------------------

@router.get("/marcas", response_model=list[MarcaOut])
def listar_marcas_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> list[MarcaOut]:
    return listar_marcas(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/marcas", response_model=MarcaOut)
def crear_marca_endpoint(
    body: MarcaCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> MarcaOut:
    return crear_marca_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.patch("/marcas/{marca_id}", response_model=MarcaOut)
def actualizar_marca_endpoint(
    marca_id: str,
    body: MarcaUpdate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> MarcaOut:
    return actualizar_marca_para_endpoint(marca_id=marca_id, drogueria_id=usuario.drogueria_id, body=body)


# -- envases ---------------------------------------------------------------------

@router.get("/envases", response_model=list[EnvaseOut])
def listar_envases_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> list[EnvaseOut]:
    return listar_envases(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/envases", response_model=EnvaseOut)
def crear_envase_endpoint(
    body: EnvaseCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> EnvaseOut:
    return crear_envase_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.patch("/envases/{envase_id}", response_model=EnvaseOut)
def actualizar_envase_endpoint(
    envase_id: str,
    body: EnvaseUpdate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> EnvaseOut:
    return actualizar_envase_para_endpoint(envase_id=envase_id, drogueria_id=usuario.drogueria_id, body=body)


# -- caracteristicas (catalogo) ---------------------------------------------------

@router.get("/caracteristicas", response_model=list[CaracteristicaOut])
def listar_caracteristicas_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
    user_client: Client = Depends(get_user_client),
) -> list[CaracteristicaOut]:
    return listar_caracteristicas(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/caracteristicas", response_model=CaracteristicaOut)
def crear_caracteristica_endpoint(
    body: CaracteristicaCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> CaracteristicaOut:
    return crear_caracteristica_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.patch("/caracteristicas/{caracteristica_id}", response_model=CaracteristicaOut)
def actualizar_caracteristica_endpoint(
    caracteristica_id: str,
    body: CaracteristicaUpdate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.categorias.escribir")),
) -> CaracteristicaOut:
    return actualizar_caracteristica_para_endpoint(
        caracteristica_id=caracteristica_id, drogueria_id=usuario.drogueria_id, body=body
    )


# -- caracteristicas de un producto (asignacion N:M) ------------------------------

@router.get("/productos/{producto_id}/caracteristicas", response_model=list[ProductoCaracteristicaOut])
def listar_caracteristicas_producto_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
) -> list[ProductoCaracteristicaOut]:
    return listar_caracteristicas_producto_para_endpoint(
        producto_id=producto_id, drogueria_id=usuario.drogueria_id
    )


@router.post("/productos/{producto_id}/caracteristicas", response_model=ProductoCaracteristicaOut)
def asignar_caracteristica_producto_endpoint(
    producto_id: str,
    body: ProductoCaracteristicaCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.escribir")),
) -> ProductoCaracteristicaOut:
    return asignar_caracteristica_producto_para_endpoint(
        producto_id=producto_id, drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.delete("/productos/{producto_id}/caracteristicas/{caracteristica_id}", status_code=204)
def quitar_caracteristica_producto_endpoint(
    producto_id: str,
    caracteristica_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.escribir")),
) -> None:
    quitar_caracteristica_producto_para_endpoint(
        producto_id=producto_id, caracteristica_id=caracteristica_id, drogueria_id=usuario.drogueria_id
    )


# -- costos ------------------------------------------------------------------------

@router.get("/productos/{producto_id}/costos", response_model=list[CostoOut])
def listar_costos_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.costos.leer")),
) -> list[CostoOut]:
    return listar_costos_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id)


# -- stock -----------------------------------------------------------------------

@router.get("/productos/{producto_id}/stock", response_model=list[StockOut])
def listar_stock_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("productos.leer")),
) -> list[StockOut]:
    return listar_stock_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id)
