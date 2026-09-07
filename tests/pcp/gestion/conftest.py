import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Como tests/conftest.py::crear_usuario_autenticado, pero devuelve el
    access_token crudo en vez de un Client ya autenticado -- 4.9 necesita el
    token para armar el header `Authorization` de un request HTTP real via
    TestClient (require_roles() solo se ejercita de verdad a través del ciclo
    completo de FastAPI, no llamando al endpoint directamente en Python).
    No se reutiliza `crear_usuario_autenticado` porque cambiar su forma de
    retorno rompería a sus consumidores existentes (tests/extraccion,
    tests/pcp/historial)."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-gestion-router-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {"id": usuario_id, "drogueria_id": drogueria_id, "rol": rol, "nombre": "Router test"}
        ).execute()

        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        return usuario_id, sesion.session.access_token

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)
