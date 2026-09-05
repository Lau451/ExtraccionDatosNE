from fastapi import APIRouter, Depends
from supabase import Client

from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client
from services.terceros.identidad.models import (
    ClienteRolCreate,
    ClienteRolOut,
    ClienteRolUpdate,
    ProveedorRolCreate,
    ProveedorRolOut,
    ProveedorRolUpdate,
    TerceroCreate,
    TerceroOut,
    TerceroUpdate,
)
from services.terceros.identidad.service import (
    actualizar_rol_cliente_para_endpoint,
    actualizar_rol_proveedor_para_endpoint,
    actualizar_tercero_para_endpoint,
    asignar_rol_cliente_para_endpoint,
    asignar_rol_proveedor_para_endpoint,
    crear_tercero_para_endpoint,
    listar_terceros,
    obtener_rol_cliente,
    obtener_rol_proveedor,
    obtener_tercero,
)

router = APIRouter()

# D3/RLS (0008_terceros_modelo.sql: terceros_ins/terceros_upd): mismo set de
# roles con permiso de escritura sobre terceros.
_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


def _es_superadmin(usuario: UsuarioPerfil) -> bool:
    return usuario.rol == "superadmin"


@router.get("/terceros", response_model=list[TerceroOut])
def listar_terceros_endpoint(
    activo: bool | None = True,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[TerceroOut]:
    return listar_terceros(user_client, drogueria_id=usuario.drogueria_id, activo=activo)


@router.post("/terceros", response_model=TerceroOut)
def crear_tercero_endpoint(
    body: TerceroCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroOut:
    return crear_tercero_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.get("/terceros/{tercero_id}", response_model=TerceroOut)
def obtener_tercero_endpoint(
    tercero_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> TerceroOut:
    return obtener_tercero(
        user_client,
        tercero_id=tercero_id,
        drogueria_id=usuario.drogueria_id,
        es_superadmin=_es_superadmin(usuario),
    )


@router.patch("/terceros/{tercero_id}", response_model=TerceroOut)
def actualizar_tercero_endpoint(
    tercero_id: str,
    body: TerceroUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> TerceroOut:
    return actualizar_tercero_para_endpoint(
        tercero_id=tercero_id,
        drogueria_id=usuario.drogueria_id,
        body=body,
        usuario_id=usuario.id,
        es_superadmin=_es_superadmin(usuario),
    )


@router.post("/terceros/{tercero_id}/clientes", response_model=ClienteRolOut)
def asignar_rol_cliente_endpoint(
    tercero_id: str,
    body: ClienteRolCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ClienteRolOut:
    return asignar_rol_cliente_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/terceros/{tercero_id}/clientes", response_model=ClienteRolOut)
def obtener_rol_cliente_endpoint(
    tercero_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> ClienteRolOut:
    return obtener_rol_cliente(user_client, tercero_id=tercero_id, drogueria_id=usuario.drogueria_id)


@router.patch("/terceros/{tercero_id}/clientes", response_model=ClienteRolOut)
def actualizar_rol_cliente_endpoint(
    tercero_id: str,
    body: ClienteRolUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ClienteRolOut:
    return actualizar_rol_cliente_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.post("/terceros/{tercero_id}/proveedores", response_model=ProveedorRolOut)
def asignar_rol_proveedor_endpoint(
    tercero_id: str,
    body: ProveedorRolCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ProveedorRolOut:
    return asignar_rol_proveedor_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )


@router.get("/terceros/{tercero_id}/proveedores", response_model=ProveedorRolOut)
def obtener_rol_proveedor_endpoint(
    tercero_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> ProveedorRolOut:
    return obtener_rol_proveedor(user_client, tercero_id=tercero_id, drogueria_id=usuario.drogueria_id)


@router.patch("/terceros/{tercero_id}/proveedores", response_model=ProveedorRolOut)
def actualizar_rol_proveedor_endpoint(
    tercero_id: str,
    body: ProveedorRolUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> ProveedorRolOut:
    return actualizar_rol_proveedor_para_endpoint(
        tercero_id=tercero_id, drogueria_id=usuario.drogueria_id, body=body
    )
