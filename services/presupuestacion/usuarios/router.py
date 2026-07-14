from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.usuarios.models import UsuarioCreate, UsuarioOut, UsuarioRolUpdate
from services.presupuestacion.usuarios.service import cambiar_rol_para_endpoint, crear_usuario_para_endpoint

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
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> UsuarioOut:
    resultado = user_client.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute()
    if not resultado.data:
        raise NotFoundError("No se encontró el usuario")
    return resultado.data[0]


@router.post("/usuarios", response_model=UsuarioOut)
def crear_usuario_endpoint(
    body: UsuarioCreate, usuario: UsuarioPerfil = Depends(require_roles("superadmin", "admin"))
) -> UsuarioOut:
    return crear_usuario_para_endpoint(creador=usuario, body=body)


@router.patch("/usuarios/{usuario_id}/rol", response_model=UsuarioOut)
def cambiar_rol_endpoint(
    usuario_id: str,
    body: UsuarioRolUpdate,
    usuario: UsuarioPerfil = Depends(require_roles("superadmin", "admin")),
) -> UsuarioOut:
    return cambiar_rol_para_endpoint(creador=usuario, usuario_id=usuario_id, nuevo_rol=body.rol)
