from fastapi import APIRouter, Depends

from services.presupuestacion.auth.models import CambiarPasswordIn, LoginIn, LoginOut
from services.presupuestacion.auth.service import cambiar_password_para_endpoint, login_para_endpoint
from services.presupuestacion.core.auth import UsuarioPerfil
from services.shared.auth import get_current_user_con_password_pendiente

router = APIRouter()


@router.post("/auth/login", response_model=LoginOut)
def login_endpoint(body: LoginIn) -> LoginOut:
    # Público: es el que emite el token.
    return login_para_endpoint(body=body)


@router.post("/auth/cambiar-password", status_code=204)
def cambiar_password_endpoint(
    body: CambiarPasswordIn,
    # Permitido con un cambio de contraseña pendiente: es la salida del bloqueo (S3).
    usuario: UsuarioPerfil = Depends(get_current_user_con_password_pendiente),
) -> None:
    cambiar_password_para_endpoint(usuario=usuario, body=body)
