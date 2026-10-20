import httpx
from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import (
    AuthApiError,
    AuthError,
    AuthInvalidCredentialsError,
    AuthRetryableError,
    AuthUnknownError,
    CustomAuthError,
)
from supabase_auth.types import Session

from services.presupuestacion.core.config import get_settings
from services.shared.exceptions import (
    DomainError,
    RateLimitError,
    ServicioExternoNoDisponibleError,
)
from services.shared.http_client import build_resilient_httpx_client

# odd/tasks/login-usuario-alta-admin.md S8: el límite de Supabase Auth no se
# disfraza de credenciales inválidas.
MENSAJE_RATE_LIMIT = "Demasiados intentos. Probá de nuevo en unos minutos."
# S12: Auth caído o con un error propio no se disfraza de credenciales ni sale como 500.
MENSAJE_AUTH_NO_DISPONIBLE = (
    "El servicio de autenticación no está disponible. Probá de nuevo en unos minutos."
)


def _status_http(exc: AuthError) -> int | None:
    if isinstance(exc, (AuthApiError, CustomAuthError)):
        return exc.status
    # AuthUnknownError (body no JSON) no trae status: gotrue la lanza dentro del
    # except del HTTPStatusError (gotrue_base_api._request), que queda en __context__.
    causa = exc.__cause__ or exc.__context__
    if isinstance(causa, httpx.HTTPStatusError):
        return causa.response.status_code
    return None


def _error_de_servicio(exc: AuthError) -> DomainError | None:
    """429 -> RateLimitError (S8); Auth inalcanzable, 5xx o body no parseable ->
    ServicioExternoNoDisponibleError (S12). None = error de credenciales/datos."""
    status = _status_http(exc)
    if status == 429:
        return RateLimitError(MENSAJE_RATE_LIMIT)
    if isinstance(exc, (AuthRetryableError, AuthUnknownError)) or (status or 0) >= 500:
        return ServicioExternoNoDisponibleError(MENSAJE_AUTH_NO_DISPONIBLE)
    return None


def obtener_email_auth(client: Client, *, usuario_id: str) -> str | None:
    """Email interno de la cuenta de Auth. Nunca sale del backend
    (odd/tasks/login-usuario-alta-admin.md S1). None si la cuenta no existe;
    RateLimitError / ServicioExternoNoDisponibleError si Auth no responde bien."""
    try:
        respuesta = client.auth.admin.get_user_by_id(usuario_id)
    except AuthError as exc:
        error = _error_de_servicio(exc)
        if error is not None:
            raise error from exc
        if isinstance(exc, AuthApiError):
            return None
        raise
    except httpx.RequestError as exc:
        # gotrue no envuelve los errores de red (solo HTTPStatusError/RuntimeError).
        raise ServicioExternoNoDisponibleError(MENSAJE_AUTH_NO_DISPONIBLE) from exc
    return respuesta.user.email if respuesta and respuesta.user else None


def iniciar_sesion(*, email: str, password: str) -> Session | None:
    """Sign-in con un cliente anon NUEVO por llamada: sign_in_with_password guarda
    la sesión en el propio cliente, así que usar el service client o los cacheados
    por token (services/shared/database.py) los dejaría autenticados como este
    usuario. Devuelve None si las credenciales no son válidas; RateLimitError si
    Supabase Auth responde 429; ServicioExternoNoDisponibleError si no responde,
    responde 5xx o un body no parseable (S12)."""
    settings = get_settings()
    # httpx propio para poder cerrarlo: el cliente se descarta al terminar y no
    # debe dejar conexiones abiertas por cada login.
    http = build_resilient_httpx_client()
    cliente = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(
            persist_session=False, auto_refresh_token=False, httpx_client=http
        ),
    )
    try:
        respuesta = cliente.auth.sign_in_with_password({"email": email, "password": password})
    except AuthError as exc:
        error = _error_de_servicio(exc)
        if error is not None:
            raise error from exc
        # AuthInvalidCredentialsError: gotrue la lanza antes del HTTP (p.ej.
        # password vacía) y no es un AuthApiError; también es el 401 genérico.
        if isinstance(exc, (AuthApiError, AuthInvalidCredentialsError)):
            return None
        raise
    except httpx.RequestError as exc:
        raise ServicioExternoNoDisponibleError(MENSAJE_AUTH_NO_DISPONIBLE) from exc
    finally:
        http.close()
    return respuesta.session
