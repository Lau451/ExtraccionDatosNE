from fastapi import APIRouter, Depends
from supabase import Client

from services.pcp.catalogo.models import ProductoProveedorCreate, ProductoProveedorOut
from services.pcp.catalogo.service import agregar_proveedor_para_endpoint, listar_proveedores_producto
from services.shared.auth import UsuarioPerfil, require_capacidad
from services.shared.database import get_user_client

router = APIRouter()


def _es_superadmin(usuario: UsuarioPerfil) -> bool:
    return usuario.rol == "superadmin"


@router.get(
    "/pcp/catalogo/productos/{producto_id}/proveedores",
    response_model=list[ProductoProveedorOut],
)
def listar_proveedores_producto_endpoint(
    producto_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("pcp.leer")),
    user_client: Client = Depends(get_user_client),
) -> list[ProductoProveedorOut]:
    return listar_proveedores_producto(
        user_client,
        producto_id=producto_id,
        drogueria_id=usuario.drogueria_id,
        es_superadmin=_es_superadmin(usuario),
    )


@router.post(
    "/pcp/catalogo/productos/{producto_id}/proveedores",
    response_model=ProductoProveedorOut,
)
def agregar_proveedor_endpoint(
    producto_id: str,
    body: ProductoProveedorCreate,
    usuario: UsuarioPerfil = Depends(require_capacidad("pcp.escribir")),
) -> ProductoProveedorOut:
    return agregar_proveedor_para_endpoint(
        drogueria_id=usuario.drogueria_id, producto_id=producto_id, body=body, usuario_id=usuario.id
    )
