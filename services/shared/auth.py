# Extraído de services/presupuestacion/core/auth.py (migración terceros-modelo,
# D5): services/terceros/*/router.py necesita UsuarioPerfil/require_roles para
# exponer sus propios endpoints sin importar services.presupuestacion. El
# blocker original de D5 solo mencionaba config/database/exceptions, pero
# auth.py tiene el mismo problema en cuanto Fase 3 crea routers reales. Mismo
# criterio: se extrae acá y services/presupuestacion/core/auth.py queda como
# shim de reexport para no romper los ~20 imports existentes.
from typing import Callable

from fastapi import Depends
from pydantic import BaseModel
from supabase import Client

from services.shared.auth_jwt import TokenInvalidoError, verificar_token
from services.shared.config import get_settings
from services.shared.database import get_bearer_token, get_user_client
from services.shared.exceptions import AuthenticationError, ForbiddenError, NotFoundError


class UserClaims(BaseModel):
    sub: str
    exp: int


MENSAJE_CAMBIO_PASSWORD_PENDIENTE = "Debés cambiar tu contraseña antes de continuar"


class UsuarioPerfil(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    activo: bool = True
    debe_cambiar_password: bool = False


def get_current_claims(token: str = Depends(get_bearer_token)) -> UserClaims:
    try:
        payload = verificar_token(token, supabase_url=get_settings().supabase_url)
    except TokenInvalidoError as exc:
        raise AuthenticationError("Token inválido o vencido") from exc
    return UserClaims(sub=payload["sub"], exp=payload["exp"])


def _cargar_perfil(claims: UserClaims, client: Client) -> UsuarioPerfil:
    result = (
        client.table("usuarios")
        .select("id, drogueria_id, rol, activo, debe_cambiar_password")
        .eq("id", claims.sub)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise NotFoundError("No se encontró el perfil de usuario")
    perfil = UsuarioPerfil(**result.data[0])
    if not perfil.activo:
        raise AuthenticationError("Usuario desactivado")
    return perfil


def exigir_password_al_dia(perfil: UsuarioPerfil) -> None:
    if perfil.debe_cambiar_password:
        raise ForbiddenError(MENSAJE_CAMBIO_PASSWORD_PENDIENTE)


def get_current_user(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil:
    # Una cuenta creada o blanqueada por un admin queda bloqueada hasta que cambie
    # la contraseña (odd/tasks/login-usuario-alta-admin.md S3).
    perfil = _cargar_perfil(claims, client)
    exigir_password_al_dia(perfil)
    return perfil


def get_current_user_con_password_pendiente(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil:
    """Como get_current_user pero sin el bloqueo por cambio de contraseña pendiente.
    Solo para las excepciones de S3: leer el propio perfil y cambiar la propia
    contraseña. Cualquier otro endpoint usa get_current_user."""
    return _cargar_perfil(claims, client)


def require_roles(*roles: str) -> Callable[..., UsuarioPerfil]:
    def _dependency(usuario: UsuarioPerfil = Depends(get_current_user)) -> UsuarioPerfil:
        if usuario.rol not in roles:
            raise ForbiddenError("No tenés permisos para esta acción")
        return usuario

    return _dependency
