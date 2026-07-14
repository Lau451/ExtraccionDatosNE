from typing import Any

from supabase import Client


def crear_usuario_auth(client: Client, *, email: str, password: str) -> str:
    respuesta = client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    return respuesta.user.id


def crear_perfil_usuario(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("usuarios").insert(fila).execute().data[0]


def obtener_usuario(client: Client, *, usuario_id: str) -> dict[str, Any] | None:
    resultado = client.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def actualizar_rol(client: Client, *, usuario_id: str, rol: str) -> dict[str, Any]:
    return client.table("usuarios").update({"rol": rol}).eq("id", usuario_id).execute().data[0]
