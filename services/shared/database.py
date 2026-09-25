from functools import lru_cache

from fastapi import Depends, Header
from supabase import Client, ClientOptions, create_client

from services.shared.config import get_settings
from services.shared.exceptions import AuthenticationError
from services.shared.http_client import build_resilient_httpx_client


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
    # http2=False: ver services/shared/http_client.py -- evita reusar una conexión
    # pooled que Supabase cerró mientras el proceso estaba ocupado.
    return create_client(
        settings.supabase_url,
        settings.supabase_service_key,
        options=ClientOptions(httpx_client=build_resilient_httpx_client()),
    )


@lru_cache(maxsize=256)
def _cliente_por_token(token: str) -> Client:
    # Un Client nuevo por request paga de nuevo el handshake TLS completo a
    # Supabase en cada llamada -- medido en vivo: ~650-750ms en un Client
    # recién creado contra ~200ms reusando uno ya caliente (ver mem discovery
    # "PCP delay"). Cachear por token (nunca un único Client compartido entre
    # tokens) es obligatorio: SyncPostgrestClient.auth() escribe
    # self.headers["Authorization"] en el propio objeto, así que reusar una
    # instancia entre usuarios distintos filtraría el token de uno al pedido
    # de otro. maxsize acota el crecimiento a medida que rotan usuarios/tokens.
    settings = get_settings()
    # http2=False: ver services/shared/http_client.py -- evita reusar una conexión
    # pooled que Supabase cerró mientras el proceso estaba ocupado.
    client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(httpx_client=build_resilient_httpx_client()),
    )
    client.postgrest.auth(token)
    return client


def get_user_client(token: str = Depends(get_bearer_token)) -> Client:
    return _cliente_por_token(token)
