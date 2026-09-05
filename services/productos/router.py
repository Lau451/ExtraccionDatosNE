from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.productos.models import (
    CategoriaCreate,
    CategoriaOut,
    CategoriaUpdate,
    CostoCreate,
    CostoOut,
    ProductoCreate,
    ProductoOut,
    ProductoUpdate,
    StockAjuste,
    StockOut,
)
from services.productos.service import (
    actualizar_categoria_para_endpoint,
    actualizar_producto_para_endpoint,
    ajustar_stock_para_endpoint,
    crear_categoria_para_endpoint,
    crear_costo_para_endpoint,
    crear_producto_para_endpoint,
    eliminar_producto_para_endpoint,
    listar_categorias,
    listar_costos_para_endpoint,
    listar_productos,
    listar_stock_para_endpoint,
    obtener_producto,
)

router = APIRouter()

_ROLES_LECTURA_CATALOGO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_ESCRITURA_CATALOGO = ("admin", "gerencia", "compras")
_ROLES_ESCRITURA_CATEGORIAS = ("admin", "gerencia")
_ROLES_LECTURA_COSTOS = ("superadmin", "admin", "gerencia", "compras")


# -- productos ---------------------------------------------------------------

@router.get("/productos", response_model=list[ProductoOut])
def listar_productos_endpoint(
    activo: bool | None = None,
    categoria_id: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA_CATALOGO)),
    user_client: Client = Depends(get_user_client),
) -> list[ProductoOut]:
    return listar_productos(
        user_client, drogueria_id=usuario.drogueria_id, activo=activo, categoria_id=categoria_id
    )


@router.post("/productos", response_model=ProductoOut)
def crear_producto_endpoint(
    body: ProductoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATALOGO)),
) -> ProductoOut:
    return crear_producto_para_endpoint(drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id)


@router.get("/productos/{producto_id}", response_model=ProductoOut)
def obtener_producto_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA_CATALOGO)),
    user_client: Client = Depends(get_user_client),
) -> ProductoOut:
    return obtener_producto(user_client, producto_id=producto_id, drogueria_id=usuario.drogueria_id)


@router.patch("/productos/{producto_id}", response_model=ProductoOut)
def actualizar_producto_endpoint(
    producto_id: str,
    body: ProductoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATALOGO)),
) -> ProductoOut:
    return actualizar_producto_para_endpoint(
        producto_id=producto_id, drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.delete("/productos/{producto_id}", status_code=204)
def eliminar_producto_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles("admin", "gerencia")),
) -> None:
    eliminar_producto_para_endpoint(
        producto_id=producto_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id
    )


# -- categorias ----------------------------------------------------------------

@router.get("/categorias", response_model=list[CategoriaOut])
def listar_categorias_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA_CATALOGO)),
    user_client: Client = Depends(get_user_client),
) -> list[CategoriaOut]:
    return listar_categorias(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/categorias", response_model=CategoriaOut)
def crear_categoria_endpoint(
    body: CategoriaCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATEGORIAS)),
) -> CategoriaOut:
    return crear_categoria_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)


@router.patch("/categorias/{categoria_id}", response_model=CategoriaOut)
def actualizar_categoria_endpoint(
    categoria_id: str,
    body: CategoriaUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATEGORIAS)),
) -> CategoriaOut:
    return actualizar_categoria_para_endpoint(
        categoria_id=categoria_id, drogueria_id=usuario.drogueria_id, body=body
    )


# -- costos ------------------------------------------------------------------------

@router.get("/productos/{producto_id}/costos", response_model=list[CostoOut])
def listar_costos_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA_COSTOS)),
) -> list[CostoOut]:
    return listar_costos_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id)


@router.post("/productos/{producto_id}/costos", response_model=CostoOut)
def crear_costo_endpoint(
    producto_id: str,
    body: CostoCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATALOGO)),
) -> CostoOut:
    return crear_costo_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id, body=body)


# -- stock -----------------------------------------------------------------------

@router.get("/productos/{producto_id}/stock", response_model=list[StockOut])
def listar_stock_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA_CATALOGO)),
) -> list[StockOut]:
    return listar_stock_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id)


@router.patch("/productos/{producto_id}/stock", response_model=StockOut)
def ajustar_stock_endpoint(
    producto_id: str,
    body: StockAjuste,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA_CATALOGO)),
) -> StockOut:
    return ajustar_stock_para_endpoint(producto_id=producto_id, drogueria_id=usuario.drogueria_id, body=body)
