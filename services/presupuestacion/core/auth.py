from functools import lru_cache
from typing import Callable

import jwt
from fastapi import Depends
from jwt import PyJWKClient
from pydantic import BaseModel
from supabase import Client

from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_bearer_token, get_user_client
from services.presupuestacion.core.exceptions import AuthenticationError, ForbiddenError, NotFoundError


class UserClaims(BaseModel):
    sub: str
    exp: int


class UsuarioPerfil(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str


@lru_cache
def _get_jwk_client() -> PyJWKClient:
    settings = get_settings()
    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url)


def get_current_claims(token: str = Depends(get_bearer_token)) -> UserClaims:
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token inválido o vencido") from exc
    return UserClaims(sub=payload["sub"], exp=payload["exp"])


def get_current_user(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil:
    result = (
        client.table("usuarios")
        .select("id, drogueria_id, rol")
        .eq("id", claims.sub)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise NotFoundError("No se encontró el perfil de usuario")
    return UsuarioPerfil(**result.data[0])


def require_roles(*roles: str) -> Callable[..., UsuarioPerfil]:
    def _dependency(usuario: UsuarioPerfil = Depends(get_current_user)) -> UsuarioPerfil:
        if usuario.rol not in roles:
            raise ForbiddenError("No tenés permisos para esta acción")
        return usuario

    return _dependency
