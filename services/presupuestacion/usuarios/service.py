from typing import Any

from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios.models import UsuarioCreate, UsuarioPerfilUpdate

ROLES_GESTION_USUARIOS = ("superadmin", "admin", "gerencia")

# gerencia solo gestiona usuarios de estos roles ("solo roles inferiores",
# odd/tasks/roles-permisos-matriz.md S7): nunca admin, superadmin ni sistema.
ROLES_GESTIONABLES_POR_GERENCIA = ("gerencia", "lider_comercial", "comercial", "compras")


def _validar_objetivo_de_gerencia(creador: UsuarioPerfil, objetivo: dict[str, Any]) -> None:
    if creador.rol == "gerencia" and objetivo["rol"] not in ROLES_GESTIONABLES_POR_GERENCIA:
        raise ForbiddenError("Gerencia solo puede gestionar usuarios de roles inferiores a admin")


def _mensaje_otra_drogueria(creador: UsuarioPerfil, accion: str) -> str:
    # admin conserva el texto previo a S7; gerencia recibe uno propio.
    if creador.rol == "admin":
        return f"Un admin solo puede {accion} usuarios de su droguería"
    return f"Gerencia solo puede {accion} usuarios de su droguería"


def crear_usuario(client: Client, *, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]:
    if creador.rol not in ROLES_GESTION_USUARIOS:
        raise ForbiddenError("Solo superadmin, admin o gerencia pueden crear usuarios")

    if body.rol in ("superadmin", "admin") and creador.rol != "superadmin":
        raise ForbiddenError("Solo superadmin puede crear usuarios con rol superadmin o admin")

    if creador.rol == "gerencia" and body.rol not in ROLES_GESTIONABLES_POR_GERENCIA:
        raise ForbiddenError("Gerencia solo puede crear usuarios de roles inferiores a admin")

    if creador.rol in ("admin", "gerencia"):
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
    if creador.rol not in ROLES_GESTION_USUARIOS:
        raise ForbiddenError("Solo superadmin, admin o gerencia pueden cambiar roles")

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

    _validar_objetivo_de_gerencia(creador, objetivo)
    if creador.rol == "gerencia" and nuevo_rol not in ROLES_GESTIONABLES_POR_GERENCIA:
        raise ForbiddenError("Gerencia solo puede asignar roles inferiores a admin")

    if creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError(_mensaje_otra_drogueria(creador, "modificar"))

    return repo.actualizar_rol(client, usuario_id=usuario_id, rol=nuevo_rol)


def cambiar_activo(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, activo: bool
) -> dict[str, Any]:
    if creador.rol not in ROLES_GESTION_USUARIOS:
        raise ForbiddenError("Solo superadmin, admin o gerencia pueden activar/desactivar usuarios")

    if usuario_id == creador.id:
        raise ForbiddenError("No podés activar/desactivar tu propio usuario")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema"):
        raise ForbiddenError("No se puede activar/desactivar un superadmin o sistema por esta vía")

    _validar_objetivo_de_gerencia(creador, objetivo)

    if creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError(_mensaje_otra_drogueria(creador, "modificar"))

    return repo.actualizar_activo(client, usuario_id=usuario_id, activo=activo)


def eliminar_usuario(client: Client, *, creador: UsuarioPerfil, usuario_id: str) -> None:
    if creador.rol not in ROLES_GESTION_USUARIOS:
        raise ForbiddenError("Solo superadmin, admin o gerencia pueden eliminar usuarios")

    if usuario_id == creador.id:
        raise ForbiddenError("No podés eliminar tu propio usuario")

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema"):
        raise ForbiddenError("No se puede eliminar un superadmin o sistema por esta vía")

    _validar_objetivo_de_gerencia(creador, objetivo)

    if creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError(_mensaje_otra_drogueria(creador, "eliminar"))

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
