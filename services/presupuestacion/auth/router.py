from fastapi import APIRouter, Depends

from services.presupuestacion.auth.models import CambiarPasswordIn, CapacidadesOut, LoginIn, LoginOut
from services.presupuestacion.auth.service import cambiar_password_para_endpoint, login_para_endpoint
from services.presupuestacion.core.auth import UsuarioPerfil
from services.shared.auth import get_current_user, get_current_user_con_password_pendiente
from services.shared.permisos import capacidades_de

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


@router.get("/auth/capacidades", response_model=CapacidadesOut)
def capacidades_endpoint(usuario: UsuarioPerfil = Depends(get_current_user)) -> CapacidadesOut:
    # Para el menú y las acciones del frontend; cada endpoint vuelve a verificar
    # (odd/tasks/roles-capacidades.md S4). Con un cambio de contraseña pendiente
    # queda bloqueado como cualquier endpoint (L5).
    return CapacidadesOut(rol=usuario.rol, capacidades=capacidades_de(usuario.rol))
