from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.usuarios.models import (
    UsuarioActivoUpdate,
    UsuarioCreate,
    UsuarioOut,
    UsuarioPasswordUpdate,
    UsuarioPerfilUpdate,
    UsuarioRolUpdate,
    UsuarioUsernameUpdate,
)
from services.presupuestacion.usuarios.service import (
    ROLES_GESTION_USUARIOS,
    actualizar_perfil_propio_para_endpoint,
    blanquear_password_para_endpoint,
    cambiar_activo_para_endpoint,
    cambiar_rol_para_endpoint,
    cambiar_username_para_endpoint,
    crear_usuario_para_endpoint,
    eliminar_usuario_para_endpoint,
)
from services.shared.auth import exigir_password_al_dia, get_current_user_con_password_pendiente

router = APIRouter()


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[UsuarioOut]:
    return user_client.table("usuarios").select("*").order("nombre").execute().data


@router.get("/usuarios/{usuario_id}", response_model=UsuarioOut)
def obtener_usuario_endpoint(
    usuario_id: str,
    usuario: UsuarioPerfil = Depends(get_current_user_con_password_pendiente),
    user_client: Client = Depends(get_user_client),
) -> UsuarioOut:
    # Con un cambio de contraseña pendiente solo se puede leer el propio perfil
    # (odd/tasks/login-usuario-alta-admin.md S3).
    if usuario_id != usuario.id:
        exigir_password_al_dia(usuario)
    resultado = user_client.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute()
    if not resultado.data:
        raise NotFoundError("No se encontró el usuario")
    return resultado.data[0]


@router.post("/usuarios", response_model=UsuarioOut)
def crear_usuario_endpoint(
    body: UsuarioCreate, usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS))
) -> UsuarioOut:
    return crear_usuario_para_endpoint(creador=usuario, body=body)


@router.patch("/usuarios/{usuario_id}/rol", response_model=UsuarioOut)
def cambiar_rol_endpoint(
    usuario_id: str,
    body: UsuarioRolUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS)),
) -> UsuarioOut:
    return cambiar_rol_para_endpoint(creador=usuario, usuario_id=usuario_id, nuevo_rol=body.rol)


@router.patch("/usuarios/{usuario_id}/activo", response_model=UsuarioOut)
def cambiar_activo_endpoint(
    usuario_id: str,
    body: UsuarioActivoUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS)),
) -> UsuarioOut:
    return cambiar_activo_para_endpoint(creador=usuario, usuario_id=usuario_id, activo=body.activo)


@router.patch("/usuarios/{usuario_id}/password", response_model=UsuarioOut)
def blanquear_password_endpoint(
    usuario_id: str,
    body: UsuarioPasswordUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS)),
) -> UsuarioOut:
    return blanquear_password_para_endpoint(
        creador=usuario, usuario_id=usuario_id, password=body.password
    )


@router.patch("/usuarios/{usuario_id}/username", response_model=UsuarioOut)
def cambiar_username_endpoint(
    usuario_id: str,
    body: UsuarioUsernameUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS)),
) -> UsuarioOut:
    return cambiar_username_para_endpoint(
        creador=usuario, usuario_id=usuario_id, username=body.username
    )


@router.patch("/usuarios/me", response_model=UsuarioOut)
def actualizar_perfil_propio_endpoint(
    body: UsuarioPerfilUpdate,
    usuario: UsuarioPerfil = Depends(get_current_user),
) -> UsuarioOut:
    return actualizar_perfil_propio_para_endpoint(usuario_id=usuario.id, body=body)


@router.delete("/usuarios/{usuario_id}", status_code=204)
def eliminar_usuario_endpoint(
    usuario_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_GESTION_USUARIOS)),
) -> None:
    eliminar_usuario_para_endpoint(creador=usuario, usuario_id=usuario_id)
