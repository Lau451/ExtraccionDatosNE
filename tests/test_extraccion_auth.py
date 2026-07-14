"""Tests de la identificación opcional de usuario de services/extraccion/ —
services/extraccion/auth.py. Ver el docstring del módulo: no es un gate que bloquea,
identifica cuando puede y sigue funcionando igual que hoy cuando no."""
import pytest
from fastapi import HTTPException

from services.extraccion.auth import get_bearer_token_opcional, get_usuario_id_actual


def test_get_bearer_token_opcional_sin_header_devuelve_none():
    assert get_bearer_token_opcional(None) is None


def test_get_bearer_token_opcional_sin_esquema_bearer_levanta_401():
    with pytest.raises(HTTPException) as exc_info:
        get_bearer_token_opcional("Basic algo")
    assert exc_info.value.status_code == 401


def test_get_bearer_token_opcional_con_bearer_devuelve_el_token():
    assert get_bearer_token_opcional("Bearer mi-token") == "mi-token"


def test_get_usuario_id_actual_sin_token_devuelve_none():
    assert get_usuario_id_actual(None) is None


def test_get_usuario_id_actual_con_token_invalido_levanta_401(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    with pytest.raises(HTTPException) as exc_info:
        get_usuario_id_actual("esto-no-es-un-jwt")
    assert exc_info.value.status_code == 401


def test_get_usuario_id_actual_con_token_pero_sin_supabase_url_levanta_503(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        get_usuario_id_actual("cualquier-token")
    assert exc_info.value.status_code == 503


@pytest.mark.integration
def test_get_usuario_id_actual_con_token_real_pero_sin_perfil_devuelve_none(
    service_client, monkeypatch
):
    """Caso concreto que motivó el chequeo: un usuario de Supabase Auth con JWT
    real y válido, pero sin fila en usuarios todavía (perfil no creado). No debe
    bloquear la carga -- solo queda sin atribución.

    services/extraccion/supabase_client.py lee SUPABASE_URL/SUPABASE_SERVICE_KEY de
    os.environ directo (no vía pydantic Settings como presupuestacion/) y nada en
    este archivo de test dispara load_dotenv() -- por eso se setean explícito con
    monkeypatch y se resetea el singleton, para no depender de qué otro módulo se
    haya importado antes en la sesión de pytest."""
    import secrets
    import uuid

    from supabase import create_client

    import services.extraccion.supabase_client as sc_module
    from services.presupuestacion.core.config import get_settings

    settings = get_settings()
    monkeypatch.setenv("SUPABASE_URL", settings.supabase_url)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", settings.supabase_service_key)
    sc_module.reset_client_for_testing()

    email = f"orfano-test-{uuid.uuid4()}@seed.local"
    password = secrets.token_urlsafe(24)
    auth_response = service_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    usuario_id_auth = auth_response.user.id

    try:
        cliente_autenticado = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_autenticado.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        # Deliberadamente NO se inserta fila en usuarios -- el JWT es real y válido,
        # pero el perfil no existe.
        resultado = get_usuario_id_actual(sesion.session.access_token)
        assert resultado is None
    finally:
        service_client.auth.admin.delete_user(usuario_id_auth)
        sc_module.reset_client_for_testing()
