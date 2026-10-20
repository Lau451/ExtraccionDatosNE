from supabase import Client, ClientOptions, create_client
from supabase_auth.errors import AuthApiError, AuthInvalidCredentialsError
from supabase_auth.types import Session

from services.presupuestacion.core.config import get_settings
from services.shared.exceptions import RateLimitError
from services.shared.http_client import build_resilient_httpx_client

# odd/tasks/login-usuario-alta-admin.md S8: el límite de Supabase Auth no se
# disfraza de credenciales inválidas.
MENSAJE_RATE_LIMIT = "Demasiados intentos. Probá de nuevo en unos minutos."


def obtener_email_auth(client: Client, *, usuario_id: str) -> str | None:
    """Email interno de la cuenta de Auth. Nunca sale del backend
    (odd/tasks/login-usuario-alta-admin.md S1)."""
    try:
        respuesta = client.auth.admin.get_user_by_id(usuario_id)
    except AuthApiError:
        return None
    return respuesta.user.email if respuesta and respuesta.user else None


def iniciar_sesion(*, email: str, password: str) -> Session | None:
    """Sign-in con un cliente anon NUEVO por llamada: sign_in_with_password guarda
    la sesión en el propio cliente, así que usar el service client o los cacheados
    por token (services/shared/database.py) los dejaría autenticados como este
    usuario. Devuelve None si las credenciales no son válidas; RateLimitError si
    Supabase Auth responde 429."""
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
    except AuthApiError as exc:
        if exc.status == 429:
            raise RateLimitError(MENSAJE_RATE_LIMIT) from exc
        return None
    except AuthInvalidCredentialsError:
        # gotrue la lanza antes del HTTP (p.ej. password vacía) y no es un
        # AuthApiError: sin este catch salía como 500 en vez del 401 genérico.
        return None
    finally:
        http.close()
    return respuesta.session
