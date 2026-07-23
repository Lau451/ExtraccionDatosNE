import secrets
import uuid

import pytest
from supabase_auth.errors import AuthApiError


def _borrar_usuario_auth_si_existe(service_client, usuario_id: str) -> None:
    # El test puede haber borrado el usuario antes del teardown (ej. tests de
    # eliminar_usuario) — a diferencia del delete de la tabla `usuarios`
    # (idempotente), delete_user de Auth lanza si el id ya no existe.
    try:
        service_client.auth.admin.delete_user(usuario_id)
    except AuthApiError:
        pass


@pytest.fixture
def seed_admin(service_client, seed_drogueria):
    email = f"admin-test-{uuid.uuid4()}@seed.local"
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    usuario_id = auth_response.user.id
    fila = {
        "id": usuario_id,
        "drogueria_id": seed_drogueria["id"],
        "rol": "admin",
        "nombre": "Admin de test",
    }
    service_client.table("usuarios").insert(fila).execute()
    yield {"id": usuario_id, "rol": "admin", "drogueria_id": seed_drogueria["id"]}
    service_client.table("usuarios").delete().eq("id", usuario_id).execute()
    _borrar_usuario_auth_si_existe(service_client, usuario_id)


@pytest.fixture
def seed_superadmin(service_client):
    email = f"superadmin-test-{uuid.uuid4()}@seed.local"
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    usuario_id = auth_response.user.id
    fila = {"id": usuario_id, "drogueria_id": None, "rol": "superadmin", "nombre": "Superadmin de test"}
    service_client.table("usuarios").insert(fila).execute()
    yield {"id": usuario_id, "rol": "superadmin", "drogueria_id": None}
    service_client.table("usuarios").delete().eq("id", usuario_id).execute()
    _borrar_usuario_auth_si_existe(service_client, usuario_id)


@pytest.fixture
def limpiar_usuario_creado(service_client):
    creados = []
    yield creados
    for usuario_id in creados:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        _borrar_usuario_auth_si_existe(service_client, usuario_id)


@pytest.fixture
def crear_usuario_directo(service_client):
    """Factory de setup para tests que necesitan "un usuario ya existente" sin
    ejercitar crear_usuario (que invita por email desde la migración a
    invite_user_by_email — usarlo como scaffolding agota el rate limit de Auth
    en pocos tests). Inserta directo, igual que seed_admin/seed_superadmin."""
    creados = []

    def _crear(*, rol: str, drogueria_id: str | None, activo: bool = True) -> dict:
        email = f"directo-test-{uuid.uuid4()}@seed.local"
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        service_client.table("usuarios").insert(
            {
                "id": usuario_id,
                "drogueria_id": drogueria_id,
                "rol": rol,
                "nombre": "Usuario directo",
                "apellido": "De test",
                "activo": activo,
            }
        ).execute()
        creados.append(usuario_id)
        return {"id": usuario_id, "rol": rol, "drogueria_id": drogueria_id}

    yield _crear
    for usuario_id in creados:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        _borrar_usuario_auth_si_existe(service_client, usuario_id)
