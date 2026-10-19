from typing import Any

from supabase import Client

from services.presupuestacion.auth import repository as repo
from services.presupuestacion.auth.models import CambiarPasswordIn, LoginIn
from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import AuthenticationError, ValidationError
from services.presupuestacion.usuarios import repository as usuarios_repo
from services.presupuestacion.usuarios.service import normalizar_username, validar_password

# Mismo mensaje para username inexistente y contraseña incorrecta, así no se
# pueden sondear usernames (odd/tasks/login-usuario-alta-admin.md S1).
MENSAJE_LOGIN_INVALIDO = "Usuario o contraseña incorrectos"


def login(client: Client, *, body: LoginIn) -> dict[str, Any]:
    """Resuelve el username al email interno de Auth del lado del servidor y abre
    la sesión. Un usuario desactivado sí obtiene sesión: get_current_user lo
    rechaza después con 401 "Usuario desactivado", igual que antes de este cambio."""
    username = normalizar_username(body.username)
    if username is None:
        raise AuthenticationError(MENSAJE_LOGIN_INVALIDO)

    usuario = usuarios_repo.obtener_usuario_por_username(client, username=username)
    if usuario is None:
        raise AuthenticationError(MENSAJE_LOGIN_INVALIDO)

    email = repo.obtener_email_auth(client, usuario_id=usuario["id"])
    if email is None:
        raise AuthenticationError(MENSAJE_LOGIN_INVALIDO)

    sesion = repo.iniciar_sesion(email=email, password=body.password)
    if sesion is None:
        raise AuthenticationError(MENSAJE_LOGIN_INVALIDO)

    return {
        "access_token": sesion.access_token,
        "refresh_token": sesion.refresh_token,
        "expires_in": sesion.expires_in,
        "expires_at": sesion.expires_at,
        "token_type": sesion.token_type,
        "user": {"id": sesion.user.id},
    }


def cambiar_password(client: Client, *, usuario: UsuarioPerfil, body: CambiarPasswordIn) -> None:
    """S3: cambio de la propia contraseña (forzado tras un alta/blanqueo o
    voluntario desde Mi cuenta). Limpia debe_cambiar_password."""
    validar_password(body.password_nueva)
    if body.password_nueva == body.password_actual:
        raise ValidationError("La nueva contraseña debe ser distinta de la actual")

    email = repo.obtener_email_auth(client, usuario_id=usuario.id)
    if email is None or repo.iniciar_sesion(email=email, password=body.password_actual) is None:
        raise ValidationError("La contraseña actual es incorrecta")

    # Auth primero, flag después (S9): si falla el update del flag, el flag queda
    # en TRUE y el usuario vuelve a la pantalla de cambio (falla cerrado), nunca
    # queda desbloqueado con la contraseña temporal.
    usuarios_repo.actualizar_password_auth(client, usuario_id=usuario.id, password=body.password_nueva)
    usuarios_repo.actualizar_perfil(
        client, usuario_id=usuario.id, campos={"debe_cambiar_password": False}
    )


def login_para_endpoint(*, body: LoginIn) -> dict[str, Any]:
    return login(get_service_client(), body=body)


def cambiar_password_para_endpoint(*, usuario: UsuarioPerfil, body: CambiarPasswordIn) -> None:
    cambiar_password(get_service_client(), usuario=usuario, body=body)
