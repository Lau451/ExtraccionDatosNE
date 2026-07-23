from typing import Any

from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios.models import UsuarioCreate, UsuarioPerfilUpdate


def crear_usuario(client: Client, *, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden crear usuarios")

    if body.rol in ("superadmin", "admin") and creador.rol != "superadmin":
        raise ForbiddenError("Solo superadmin puede crear usuarios con rol superadmin o admin")

    if creador.rol == "admin":
        drogueria_id = creador.drogueria_id
    else:
        drogueria_id = body.drogueria_id

    if body.rol == "superadmin" and drogueria_id is not None:
        raise ValidationError("Un usuario superadmin no debe tener drogueria_id")
    if body.rol != "superadmin" and drogueria_id is None:
        raise ValidationError("Los usuarios no-superadmin requieren drogueria_id")

    redirect_to = f"{get_settings().frontend_url}/accept-invite"
    usuario_id = repo.invitar_usuario_auth(
        client,
        email=body.email,
        redirect_to=redirect_to,
        nombre=body.nombre,
        apellido=body.apellido,
        rol=body.rol,
    )
    return repo.crear_perfil_usuario(
        client,
        {
            "id": usuario_id,
            "drogueria_id": drogueria_id,
            "rol": body.rol,
            "nombre": body.nombre,
            "apellido": body.apellido,
            "es_sistema": False,
        },
    )


def cambiar_rol(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str
) -> dict[str, Any]:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden cambiar roles")

    if usuario_id == creador.id:
        raise ForbiddenError("No podés cambiar tu propio rol")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema") or nuevo_rol in ("superadmin", "sistema"):
        raise ForbiddenError(
            "Cambiar desde/hacia superadmin o sistema no está permitido por esta vía"
        )

    if nuevo_rol == "admin" and creador.rol != "superadmin":
        raise ForbiddenError("Solo superadmin puede asignar el rol admin")

    if creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError("Un admin solo puede modificar usuarios de su droguería")

    return repo.actualizar_rol(client, usuario_id=usuario_id, rol=nuevo_rol)


def cambiar_activo(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, activo: bool
) -> dict[str, Any]:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden activar/desactivar usuarios")

    if usuario_id == creador.id:
        raise ForbiddenError("No podés activar/desactivar tu propio usuario")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema"):
        raise ForbiddenError("No se puede activar/desactivar un superadmin o sistema por esta vía")

    if creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError("Un admin solo puede modificar usuarios de su droguería")

    return repo.actualizar_activo(client, usuario_id=usuario_id, activo=activo)


def eliminar_usuario(client: Client, *, creador: UsuarioPerfil, usuario_id: str) -> None:
    if creador.rol not in ("superadmin", "admin"):
        raise ForbiddenError("Solo superadmin o admin pueden eliminar usuarios")

    if usuario_id == creador.id:
        raise ForbiddenError("No podés eliminar tu propio usuario")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema"):
        raise ForbiddenError("No se puede eliminar un superadmin o sistema por esta vía")

    if creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError("Un admin solo puede eliminar usuarios de su droguería")

    repo.eliminar_usuario_auth(client, usuario_id=usuario_id)


def actualizar_perfil_propio(
    client: Client, *, usuario_id: str, body: UsuarioPerfilUpdate
) -> dict[str, Any]:
    """Autoservicio: cualquier usuario autenticado edita SU PROPIO nombre/apellido.
    Sin chequeo de rol — la restricción real es que el router toma usuario_id
    del propio token (get_current_user), no de un parámetro de la URL."""
    campos = body.model_dump(exclude_unset=True)
    return repo.actualizar_perfil(client, usuario_id=usuario_id, campos=campos)


def crear_usuario_para_endpoint(*, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]:
    return crear_usuario(get_service_client(), creador=creador, body=body)


def cambiar_rol_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str) -> dict[str, Any]:
    return cambiar_rol(get_service_client(), creador=creador, usuario_id=usuario_id, nuevo_rol=nuevo_rol)


def cambiar_activo_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, activo: bool) -> dict[str, Any]:
    return cambiar_activo(get_service_client(), creador=creador, usuario_id=usuario_id, activo=activo)


def actualizar_perfil_propio_para_endpoint(
    *, usuario_id: str, body: UsuarioPerfilUpdate
) -> dict[str, Any]:
    return actualizar_perfil_propio(get_service_client(), usuario_id=usuario_id, body=body)


def eliminar_usuario_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str) -> None:
    eliminar_usuario(get_service_client(), creador=creador, usuario_id=usuario_id)
