"""tests/auth/test_repository.py -- iniciar_sesion usa un cliente anon nuevo por
llamada (nunca el service client ni los clientes cacheados por token, cuya sesión
de Auth quedaría mutada). Unitario: create_client se reemplaza por un fake."""

from supabase_auth.errors import AuthApiError

from services.presupuestacion.auth import repository as auth_repo
from services.shared.config import get_settings


class _FakeAuth:
    def __init__(self, password_valida: str) -> None:
        self._password_valida = password_valida
        self.credenciales: list[dict] = []

    def sign_in_with_password(self, credenciales):
        self.credenciales.append(credenciales)
        if credenciales["password"] != self._password_valida:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")

        class _Respuesta:
            session = "sesion-nueva"

        return _Respuesta()


def _fake_create_client(creados: list):
    def _create_client(url, key, options=None):
        cliente = type("Cliente", (), {})()
        cliente.auth = _FakeAuth("correcta1")
        creados.append({"url": url, "key": key, "options": options, "cliente": cliente})
        return cliente

    return _create_client


def test_iniciar_sesion_usa_un_cliente_anon_nuevo_por_llamada(monkeypatch):
    creados: list = []
    monkeypatch.setattr(auth_repo, "create_client", _fake_create_client(creados))

    primera = auth_repo.iniciar_sesion(email="a@usuarios.local", password="correcta1")
    segunda = auth_repo.iniciar_sesion(email="a@usuarios.local", password="correcta1")

    assert primera == segunda == "sesion-nueva"
    assert len(creados) == 2
    assert creados[0]["cliente"] is not creados[1]["cliente"]
    settings = get_settings()
    assert all(c["key"] == settings.supabase_anon_key for c in creados)
    assert all(c["url"] == settings.supabase_url for c in creados)
    assert creados[0]["cliente"].auth.credenciales == [
        {"email": "a@usuarios.local", "password": "correcta1"}
    ]
    # sin persistir ni refrescar la sesión: el cliente se descarta al terminar
    assert creados[0]["options"].persist_session is False
    assert creados[0]["options"].auto_refresh_token is False


def test_iniciar_sesion_con_credenciales_invalidas_devuelve_none(monkeypatch):
    creados: list = []
    monkeypatch.setattr(auth_repo, "create_client", _fake_create_client(creados))

    assert auth_repo.iniciar_sesion(email="a@usuarios.local", password="mala") is None
