from typing import Any

from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios.models import UsuarioCreate


def crear_usuario(client: Client, *, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden crear usuarios")

    if body.rol == "superadmin" and creador.rol != "superadmin":
        raise ForbiddenError("Un admin no puede crear usuarios con rol superadmin")

    if creador.rol == "admin":
        drogueria_id = creador.drogueria_id
    else:
        drogueria_id = body.drogueria_id

    if body.rol == "superadmin" and drogueria_id is not None:
        raise ValidationError("Un usuario superadmin no debe tener drogueria_id")
    if body.rol != "superadmin" and drogueria_id is None:
        raise ValidationError("Los usuarios no-superadmin requieren drogueria_id")

    usuario_id = repo.crear_usuario_auth(client, email=body.email, password=body.password)
    return repo.crear_perfil_usuario(
        client,
        {
            "id": usuario_id,
            "drogueria_id": drogueria_id,
            "rol": body.rol,
            "nombre": body.nombre,
            "es_sistema": False,
        },
    )


def cambiar_rol(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str
) -> dict[str, Any]:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden cambiar roles")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] == "superadmin" or nuevo_rol == "superadmin":
        raise ForbiddenError("Cambiar desde/hacia superadmin no está permitido por esta vía")

    if creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError("Un admin solo puede modificar usuarios de su droguería")

    return repo.actualizar_rol(client, usuario_id=usuario_id, rol=nuevo_rol)


def crear_usuario_para_endpoint(*, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]:
    return crear_usuario(get_service_client(), creador=creador, body=body)


def cambiar_rol_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str) -> dict[str, Any]:
    return cambiar_rol(get_service_client(), creador=creador, usuario_id=usuario_id, nuevo_rol=nuevo_rol)
