import secrets
import uuid

import pytest


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
    service_client.auth.admin.delete_user(usuario_id)


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
    service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def limpiar_usuario_creado(service_client):
    creados = []
    yield creados
    for usuario_id in creados:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.auth.admin.delete_user(usuario_id)
