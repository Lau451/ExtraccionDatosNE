from typing import Any

from supabase import Client
from supabase_auth.errors import AuthApiError

from services.presupuestacion.core.exceptions import ConflictError, ValidationError


def invitar_usuario_auth(
    client: Client, *, email: str, redirect_to: str, nombre: str, apellido: str, rol: str
) -> str:
    try:
        respuesta = client.auth.admin.invite_user_by_email(
            email,
            {
                "redirect_to": redirect_to,
                "data": {"nombre": nombre, "apellido": apellido, "rol": rol},
            },
        )
    except AuthApiError as exc:
        # Sin este catch, la excepción no mapeada cae al 500 default de FastAPI,
        # que corre FUERA de CORSMiddleware (ver core/exceptions.py STATUS_MAP) —
        # el navegador lo ve como "Failed to fetch" sin ningún mensaje legible,
        # en vez de un error de dominio claro. Confirmado en sesión de testing
        # manual: rate limit de Auth (429) y "email inválido" (400) ambos
        # reproducían este síntoma antes de este catch.
        if exc.status == 429:
            raise ConflictError(
                "No se pudo enviar la invitación por email en este momento (límite de envíos "
                "alcanzado). Probá de nuevo en un rato."
            ) from exc
        raise ValidationError(f"No se pudo invitar al usuario: {exc.message}") from exc
    return respuesta.user.id


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
