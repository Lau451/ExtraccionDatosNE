import secrets
import uuid

import pytest


@pytest.fixture
def seed_usuario_sistema_2(service_client):
    """Un segundo usuario técnico, distinto de seed_usuario_sistema, para poder
    distinguir created_by (no debe cambiar en un update) de updated_by (sí)."""
    email = f"sistema-test-{uuid.uuid4()}@seed.local"
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    usuario_id = auth_response.user.id
    service_client.table("usuarios").insert(
        {
            "id": usuario_id,
            "drogueria_id": None,
            "rol": "sistema",
            "nombre": "Usuario Sistema 2 (test)",
            "es_sistema": True,
        }
    ).execute()
    yield {"id": usuario_id, "rol": "sistema"}
    service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def limpiar_catalogo_import(service_client, seed_drogueria):
    """productos/proveedores/clientes no tienen ON DELETE CASCADE desde droguerias
    (solo costos_productos/stock_productos cascadean desde producto_id) — hay que
    limpiarlos a mano antes de que seed_drogueria borre la fila padre."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("productos").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("proveedores").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("clientes").delete().eq("drogueria_id", drog_id).execute()
