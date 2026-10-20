import logging
from typing import Any

from supabase import Client
from supabase_auth.errors import AuthApiError

from services.presupuestacion.core.exceptions import ConflictError, ValidationError

logger = logging.getLogger(__name__)


def crear_usuario_auth(
    client: Client, *, email: str, password: str, nombre: str, apellido: str, rol: str
) -> str:
    # Cuenta confirmada en el acto y sin email de invitación
    # (odd/tasks/login-usuario-alta-admin.md S2): `email` es la dirección interna
    # opaca, nunca se le envía correo.
    try:
        respuesta = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"nombre": nombre, "apellido": apellido, "rol": rol},
            }
        )
    except AuthApiError as exc:
        # Sin este catch, la excepción no mapeada cae al 500 default de FastAPI,
        # que corre FUERA de CORSMiddleware (ver core/exceptions.py STATUS_MAP) —
        # el navegador lo ve como "Failed to fetch" sin ningún mensaje legible,
        # en vez de un error de dominio claro (mismo criterio que tenía la
        # invitación por email que esto reemplaza).
        if exc.status == 429:
            raise ConflictError(
                "No se pudo crear la cuenta en este momento (límite de pedidos alcanzado). "
                "Probá de nuevo en un rato."
            ) from exc
        raise ValidationError(f"No se pudo crear el usuario: {exc.message}") from exc
    return respuesta.user.id


def descartar_usuario_auth(client: Client, *, usuario_id: str) -> None:
    """Compensación del alta: borra la cuenta de Auth recién creada cuando el
    perfil no se pudo insertar. No relanza: el error original es el que importa."""
    try:
        client.auth.admin.delete_user(usuario_id)
    except AuthApiError:
        logger.exception("No se pudo borrar la cuenta de Auth huérfana %s", usuario_id)


def actualizar_password_auth(client: Client, *, usuario_id: str, password: str) -> None:
    try:
        client.auth.admin.update_user_by_id(usuario_id, {"password": password})
    except AuthApiError as exc:
        raise ValidationError(f"No se pudo cambiar la contraseña: {exc.message}") from exc


def obtener_usuario_por_username(client: Client, *, username: str) -> dict[str, Any] | None:
    # username se guarda en minúsculas (ck_usuarios_username_formato), así que
    # alcanza con comparar contra el valor ya normalizado.
    resultado = client.table("usuarios").select("*").eq("username", username).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def crear_perfil_usuario(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("usuarios").insert(fila).execute().data[0]


def obtener_usuario(client: Client, *, usuario_id: str) -> dict[str, Any] | None:
    resultado = client.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def actualizar_rol(client: Client, *, usuario_id: str, rol: str) -> dict[str, Any]:
    return client.table("usuarios").update({"rol": rol}).eq("id", usuario_id).execute().data[0]


def actualizar_activo(client: Client, *, usuario_id: str, activo: bool) -> dict[str, Any]:
    return client.table("usuarios").update({"activo": activo}).eq("id", usuario_id).execute().data[0]


def actualizar_perfil(client: Client, *, usuario_id: str, campos: dict[str, Any]) -> dict[str, Any]:
    return client.table("usuarios").update(campos).eq("id", usuario_id).execute().data[0]


def eliminar_usuario_auth(client: Client, *, usuario_id: str) -> None:
    # usuarios.id -> auth.users.id tiene ON DELETE CASCADE (rls_final.sql), así
    # que borrar acá alcanza para borrar también la fila de `usuarios`.
    try:
        client.auth.admin.delete_user(usuario_id)
    except AuthApiError as exc:
        raise ConflictError(
            "No se puede eliminar: el usuario tiene actividad asociada (eventos, historial de "
            "cambios, etc.)."
        ) from exc
