from functools import lru_cache

from fastapi import Depends, Header
from supabase import Client, create_client

from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.exceptions import AuthenticationError


def get_bearer_token(authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise AuthenticationError("Falta el header Authorization")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("El header Authorization debe ser 'Bearer <token>'")
    return token


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_user_client(token: str = Depends(get_bearer_token)) -> Client:
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(token)
    return client
