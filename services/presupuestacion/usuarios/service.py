import re
import uuid
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.config import get_settings
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios.models import UsuarioCreate, UsuarioPerfilUpdate

ROLES_GESTION_USUARIOS = ("superadmin", "admin", "gerencia")

# gerencia solo gestiona usuarios de estos roles ("solo roles inferiores",
# odd/tasks/roles-permisos-matriz.md S7): nunca admin, superadmin ni sistema.
ROLES_GESTIONABLES_POR_GERENCIA = ("gerencia", "lider_comercial", "comercial", "compras")

# odd/tasks/login-usuario-alta-admin.md S1: 3-30 caracteres de a-z 0-9 . _ -,
# guardado en minúsculas. Mismo patrón que ck_usuarios_username_formato (0038).
_PATRON_USERNAME = re.compile(r"[a-z0-9._-]{3,30}")
PASSWORD_LARGO_MINIMO = 8
_MENSAJE_USERNAME_INVALIDO = (
    "El nombre de usuario debe tener entre 3 y 30 caracteres: letras, números, "
    "punto, guion o guion bajo"
)
_MENSAJE_USERNAME_DUPLICADO = "Ya existe un usuario con ese nombre de usuario"
# unique_violation de Postgres (ux_usuarios_username_lower), para la carrera entre
# el chequeo previo y el INSERT/UPDATE.
_CODIGO_UNIQUE_VIOLATION = "23505"


def normalizar_username(username: str) -> str | None:
    """Devuelve el username en minúsculas, o None si no cumple el formato de S1."""
    normalizado = username.strip().lower()
    return normalizado if _PATRON_USERNAME.fullmatch(normalizado) else None


def validar_password(password: str) -> None:
    if len(password) < PASSWORD_LARGO_MINIMO:
        raise ValidationError(
            f"La contraseña debe tener al menos {PASSWORD_LARGO_MINIMO} caracteres"
        )


def _username_valido(username: str) -> str:
    normalizado = normalizar_username(username)
    if normalizado is None:
        raise ValidationError(_MENSAJE_USERNAME_INVALIDO)
    return normalizado


def _es_username_duplicado(exc: Exception) -> bool:
    return isinstance(exc, APIError) and exc.code == _CODIGO_UNIQUE_VIOLATION


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

    username = _username_valido(body.username)
    validar_password(body.password)
    if repo.obtener_usuario_por_username(client, username=username) is not None:
        raise ConflictError(_MENSAJE_USERNAME_DUPLICADO)

    # Email interno opaco (S2): no deriva del username, así editar el username
    # después no toca la cuenta de Auth.
    email_interno = f"{uuid.uuid4().hex}@{get_settings().auth_email_domain}"
    usuario_id = repo.crear_usuario_auth(
        client,
        email=email_interno,
        password=body.password,
        nombre=body.nombre,
        apellido=body.apellido,
        rol=body.rol,
    )
    try:
        return repo.crear_perfil_usuario(
            client,
            {
                "id": usuario_id,
                "drogueria_id": drogueria_id,
                "rol": body.rol,
                "nombre": body.nombre,
                "apellido": body.apellido,
                "es_sistema": False,
                "username": username,
                "debe_cambiar_password": True,
            },
        )
    except Exception as exc:
        # Sin perfil, la cuenta de Auth quedaría huérfana (S2).
        repo.descartar_usuario_auth(client, usuario_id=usuario_id)
        if _es_username_duplicado(exc):
            raise ConflictError(_MENSAJE_USERNAME_DUPLICADO) from exc
        raise


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


def _objetivo_gestionable(
    client: Client,
    *,
    creador: UsuarioPerfil,
    usuario_id: str,
    mensaje_propio: str,
    mensaje_protegido: str,
) -> dict[str, Any]:
    """Autorización de S4/S5, la misma que activar/desactivar: nadie sobre sí
    mismo, superadmin/sistema protegidos, gerencia solo roles inferiores y
    admin/gerencia solo su droguería."""
    if creador.rol not in ROLES_GESTION_USUARIOS:
        raise ForbiddenError("Solo superadmin, admin o gerencia pueden gestionar usuarios")

    if usuario_id == creador.id:
        raise ForbiddenError(mensaje_propio)

    objetivo = repo.obtener_usuario(client, usuario_id=usuario_id)
    if objetivo is None:
        raise NotFoundError("No se encontró el usuario")

    if objetivo["rol"] in ("superadmin", "sistema"):
        raise ForbiddenError(mensaje_protegido)

    _validar_objetivo_de_gerencia(creador, objetivo)

    if creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id:
        raise ForbiddenError(_mensaje_otra_drogueria(creador, "modificar"))

    return objetivo


def blanquear_password(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, password: str
) -> dict[str, Any]:
    """S4: nueva contraseña temporal; el usuario debe cambiarla al entrar."""
    _objetivo_gestionable(
        client,
        creador=creador,
        usuario_id=usuario_id,
        mensaje_propio="No podés blanquear tu propia contraseña",
        mensaje_protegido="No se puede blanquear la contraseña de un superadmin o sistema por esta vía",
    )
    validar_password(password)
    repo.actualizar_password_auth(client, usuario_id=usuario_id, password=password)
    return repo.actualizar_perfil(
        client, usuario_id=usuario_id, campos={"debe_cambiar_password": True}
    )


def cambiar_username(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, username: str
) -> dict[str, Any]:
    """S5: el admin corrige el username (p.ej. el derivado del email en 0038)."""
    objetivo = _objetivo_gestionable(
        client,
        creador=creador,
        usuario_id=usuario_id,
        mensaje_propio="No podés cambiar tu propio nombre de usuario",
        mensaje_protegido=(
            "No se puede cambiar el nombre de usuario de un superadmin o sistema por esta vía"
        ),
    )
    nuevo = _username_valido(username)
    existente = repo.obtener_usuario_por_username(client, username=nuevo)
    if existente is not None and existente["id"] != usuario_id:
        raise ConflictError(_MENSAJE_USERNAME_DUPLICADO)
    if nuevo == objetivo["username"]:
        return objetivo
    try:
        return repo.actualizar_perfil(client, usuario_id=usuario_id, campos={"username": nuevo})
    except APIError as exc:
        if _es_username_duplicado(exc):
            raise ConflictError(_MENSAJE_USERNAME_DUPLICADO) from exc
        raise


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


def blanquear_password_para_endpoint(
    *, creador: UsuarioPerfil, usuario_id: str, password: str
) -> dict[str, Any]:
    return blanquear_password(
        get_service_client(), creador=creador, usuario_id=usuario_id, password=password
    )


def cambiar_username_para_endpoint(
    *, creador: UsuarioPerfil, usuario_id: str, username: str
) -> dict[str, Any]:
    return cambiar_username(
        get_service_client(), creador=creador, usuario_id=usuario_id, username=username
    )


def eliminar_usuario_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str) -> None:
    eliminar_usuario(get_service_client(), creador=creador, usuario_id=usuario_id)
