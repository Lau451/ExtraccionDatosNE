"""tests/auth/test_router.py -- POST /auth/login y POST /auth/cambiar-password
(odd/tasks/login-usuario-alta-admin.md S1/S3). Unitarios: Supabase Auth y la
tabla usuarios se reemplazan por un almacén en memoria, así corren sin red."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.auth import repository as auth_repo
from services.presupuestacion.auth import service as auth_service
from services.presupuestacion.auth.router import router
from services.presupuestacion.usuarios import repository as usuarios_repo
from services.shared.auth import UserClaims, get_current_claims
from services.shared.database import get_user_client
from services.shared.exceptions import register_exception_handlers

MENSAJE_LOGIN = "Usuario o contraseña incorrectos"


class _Sesion:
    access_token = "access-jperez"
    refresh_token = "refresh-jperez"
    expires_in = 3600
    expires_at = 1_900_000_000
    token_type = "bearer"

    class user:  # noqa: N801 -- imita supabase_auth.types.Session.user
        id = "id-jperez"


@pytest.fixture
def estado(monkeypatch) -> dict:
    estado = {
        "usuarios": {
            "id-jperez": {
                "id": "id-jperez",
                "username": "jperez",
                "drogueria_id": "d-propia",
                "rol": "comercial",
                "activo": True,
                "debe_cambiar_password": True,
            },
        },
        "emails": {"id-jperez": "0f3c@usuarios.local"},
        "passwords": {"0f3c@usuarios.local": "temporal1"},
        "sign_ins": [],
        "password_updates": [],
        "perfil_updates": [],
    }

    def _por_username(client, *, username):
        return next(
            (f for f in estado["usuarios"].values() if f["username"] == username), None
        )

    def _email(client, *, usuario_id):
        return estado["emails"].get(usuario_id)

    def _iniciar_sesion(*, email, password):
        estado["sign_ins"].append((email, password))
        if estado["passwords"].get(email) != password:
            return None
        return _Sesion()

    def _actualizar_password(client, *, usuario_id, password):
        estado["password_updates"].append((usuario_id, password))
        estado["passwords"][estado["emails"][usuario_id]] = password

    def _actualizar_perfil(client, *, usuario_id, campos):
        estado["perfil_updates"].append((usuario_id, campos))
        estado["usuarios"][usuario_id].update(campos)
        return estado["usuarios"][usuario_id]

    monkeypatch.setattr(auth_service, "get_service_client", lambda: None)
    monkeypatch.setattr(usuarios_repo, "obtener_usuario_por_username", _por_username)
    monkeypatch.setattr(auth_repo, "obtener_email_auth", _email)
    monkeypatch.setattr(auth_repo, "iniciar_sesion", _iniciar_sesion)
    monkeypatch.setattr(usuarios_repo, "actualizar_password_auth", _actualizar_password)
    monkeypatch.setattr(usuarios_repo, "actualizar_perfil", _actualizar_perfil)
    return estado


class _UserClient:
    """Cliente de usuario que solo responde la lectura de perfil de get_current_user."""

    def __init__(self, estado: dict) -> None:
        self._estado = estado

    def table(self, _nombre):
        estado = self._estado

        class _Consulta:
            def select(self, *_a):
                return self

            def limit(self, *_a):
                return self

            def eq(self, _columna, valor):
                self._id = valor
                return self

            def execute(self):
                class _R:
                    pass

                r = _R()
                r.data = [estado["usuarios"][self._id]] if self._id in estado["usuarios"] else []
                return r

        return _Consulta()


def _cliente(estado: dict, sub: str | None = None) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    if sub is not None:
        app.dependency_overrides[get_current_claims] = lambda: UserClaims(sub=sub, exp=0)
        app.dependency_overrides[get_user_client] = lambda: _UserClient(estado)
    return TestClient(app)


# ---------------------------------------------------------------------------
# S1: POST /auth/login
# ---------------------------------------------------------------------------

def test_login_con_username_devuelve_la_sesion(estado):
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "temporal1"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "access_token": "access-jperez",
        "refresh_token": "refresh-jperez",
        "expires_in": 3600,
        "expires_at": 1_900_000_000,
        "token_type": "bearer",
        "user": {"id": "id-jperez"},
    }
    # el email interno se resuelve del lado del servidor y nunca sale en la respuesta
    assert "usuarios.local" not in respuesta.text
    assert estado["sign_ins"] == [("0f3c@usuarios.local", "temporal1")]


def test_login_ignora_mayusculas_del_username(estado):
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "JPerez", "password": "temporal1"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["user"] == {"id": "id-jperez"}


def test_login_usuario_inexistente_y_password_incorrecta_dan_el_mismo_error(estado):
    cliente = _cliente(estado)

    inexistente = cliente.post("/auth/login", json={"username": "nadie", "password": "temporal1"})
    incorrecta = cliente.post("/auth/login", json={"username": "jperez", "password": "otra-cosa"})

    assert inexistente.status_code == incorrecta.status_code == 401
    assert inexistente.json() == incorrecta.json() == {"detail": MENSAJE_LOGIN}
    # el usuario inexistente ni siquiera llega a Supabase Auth
    assert estado["sign_ins"] == [("0f3c@usuarios.local", "otra-cosa")]


@pytest.mark.parametrize("username", ["jp", "x" * 31, "j perez", "jperez@mail.com"])
def test_login_con_username_de_formato_invalido_da_el_error_generico(estado, username):
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": username, "password": "temporal1"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}
    assert estado["sign_ins"] == []


def test_login_sin_cuenta_auth_da_el_error_generico(estado):
    estado["emails"].clear()

    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "temporal1"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}
    assert estado["sign_ins"] == []


def test_login_es_publico(estado):
    # sin Authorization: no debe pedir token
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "temporal1"}
    )

    assert respuesta.status_code == 200


# ---------------------------------------------------------------------------
# S3: POST /auth/cambiar-password
# ---------------------------------------------------------------------------

def test_cambiar_password_con_flag_pendiente_cambia_y_limpia_el_flag(estado):
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert estado["password_updates"] == [("id-jperez", "definitiva8")]
    assert estado["usuarios"]["id-jperez"]["debe_cambiar_password"] is False
    assert estado["passwords"]["0f3c@usuarios.local"] == "definitiva8"


def test_cambiar_password_voluntario_sin_flag(estado):
    estado["usuarios"]["id-jperez"]["debe_cambiar_password"] = False

    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 204
    assert estado["password_updates"] == [("id-jperez", "definitiva8")]
    assert estado["usuarios"]["id-jperez"]["debe_cambiar_password"] is False


def _sin_cambios(estado: dict) -> None:
    assert estado["password_updates"] == []
    assert estado["perfil_updates"] == []
    assert estado["usuarios"]["id-jperez"]["debe_cambiar_password"] is True
    assert estado["passwords"]["0f3c@usuarios.local"] == "temporal1"


def test_cambiar_password_acepta_8_caracteres(estado):
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password", json={"password_actual": "temporal1", "password_nueva": "12345678"}
    )

    assert respuesta.status_code == 204
    assert estado["password_updates"] == [("id-jperez", "12345678")]


def test_cambiar_password_rechaza_7_caracteres(estado):
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password", json={"password_actual": "temporal1", "password_nueva": "1234567"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La contraseña debe tener al menos 8 caracteres"}
    _sin_cambios(estado)


def test_cambiar_password_rechaza_la_misma_password(estado):
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password", json={"password_actual": "temporal1", "password_nueva": "temporal1"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La nueva contraseña debe ser distinta de la actual"}
    _sin_cambios(estado)


def test_cambiar_password_con_password_actual_incorrecta_no_cambia_nada(estado):
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "equivocada", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La contraseña actual es incorrecta"}
    _sin_cambios(estado)


def test_cambiar_password_requiere_autenticacion(estado):
    respuesta = _cliente(estado).post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 401
    _sin_cambios(estado)


def test_cambiar_password_usuario_desactivado_sigue_recibiendo_401(estado):
    estado["usuarios"]["id-jperez"]["activo"] = False

    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "Usuario desactivado"}
    _sin_cambios(estado)
