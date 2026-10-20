"""tests/auth/test_router.py -- POST /auth/login y POST /auth/cambiar-password
(odd/tasks/login-usuario-alta-admin.md S1/S3). Unitarios: Supabase Auth y la
tabla usuarios se reemplazan por un almacén en memoria, así corren sin red."""

import httpx
import pytest
from fastapi import FastAPI
from supabase_auth.errors import AuthApiError
from fastapi.testclient import TestClient

from services.presupuestacion.auth import repository as auth_repo
from services.presupuestacion.auth import service as auth_service
from services.presupuestacion.auth.router import router
from services.presupuestacion.usuarios import repository as usuarios_repo
from services.shared.auth import UserClaims, get_current_claims
from services.shared.database import get_user_client
from services.shared.exceptions import register_exception_handlers

MENSAJE_LOGIN = "Usuario o contraseña incorrectos"
MENSAJE_RATE_LIMIT = "Demasiados intentos. Probá de nuevo en unos minutos."
# Email interno ficticio con el que intentan el sign-in los usernames que no
# resuelven a una cuenta (dominio por defecto de Settings.auth_email_domain).
EMAIL_LOGIN_INEXISTENTE = "login-inexistente@usuarios.local"

MENSAJE_AUTH_NO_DISPONIBLE = (
    "El servicio de autenticación no está disponible. Probá de nuevo en unos minutos."
)

# La real, antes de que el fixture `estado` la reemplace: los tests de S8 la
# ejercitan con Supabase Auth simulado a nivel de create_client.
_INICIAR_SESION_REAL = auth_repo.iniciar_sesion
_OBTENER_EMAIL_AUTH_REAL = auth_repo.obtener_email_auth


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
        "lookups": [],
        "password_updates": [],
        "perfil_updates": [],
    }

    def _por_username(client, *, username):
        estado["lookups"].append(username)
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
    # el usuario inexistente también intenta el sign-in, con el email ficticio
    assert estado["sign_ins"] == [
        (EMAIL_LOGIN_INEXISTENTE, "temporal1"),
        ("0f3c@usuarios.local", "otra-cosa"),
    ]


def test_login_usuario_inexistente_intenta_el_sign_in_con_el_email_ficticio(estado):
    """S1: el username inexistente hace el mismo sign-in que uno real, contra un
    email interno que no corresponde a ninguna cuenta; aunque Auth lo aceptara,
    la respuesta es el 401 genérico."""
    estado["passwords"][EMAIL_LOGIN_INEXISTENTE] = "temporal1"

    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "nadie", "password": "temporal1"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}
    assert estado["sign_ins"] == [(EMAIL_LOGIN_INEXISTENTE, "temporal1")]
    assert EMAIL_LOGIN_INEXISTENTE not in estado["emails"].values()


@pytest.mark.parametrize("username", ["jp", "x" * 31, "j perez", "jperez@mail.com"])
def test_login_con_username_de_formato_invalido_da_el_error_generico(estado, username):
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": username, "password": "temporal1"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}
    assert estado["sign_ins"] == [(EMAIL_LOGIN_INEXISTENTE, "temporal1")]


def test_login_sin_cuenta_auth_da_el_error_generico(estado):
    estado["emails"].clear()

    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "temporal1"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}
    assert estado["sign_ins"] == [(EMAIL_LOGIN_INEXISTENTE, "temporal1")]


def test_login_sin_enumeracion_todos_los_fallos_responden_igual(estado):
    """S10b: ningún fallo de login deja distinguir si el username existe."""
    cliente = _cliente(estado)
    intentos = {
        "inexistente": {"username": "nadie", "password": "temporal1"},
        "password_incorrecta": {"username": "jperez", "password": "otra-cosa"},
        "formato_invalido": {"username": "j perez@x", "password": "temporal1"},
        "vacio": {"username": "", "password": "temporal1"},
        "existente_con_espacios_y_mayusculas": {"username": "  JPerez ", "password": "otra-cosa"},
        "inexistente_con_espacios_y_mayusculas": {"username": "  NADIE ", "password": "temporal1"},
    }

    respuestas = {caso: cliente.post("/auth/login", json=body) for caso, body in intentos.items()}

    assert {caso: r.status_code for caso, r in respuestas.items()} == dict.fromkeys(intentos, 401)
    assert {caso: r.json() for caso, r in respuestas.items()} == dict.fromkeys(
        intentos, {"detail": MENSAJE_LOGIN}
    )


def test_login_exitoso_no_expone_ningun_email(estado):
    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "  JPerez ", "password": "temporal1"}
    )

    assert respuesta.status_code == 200
    assert "@" not in respuesta.text


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


# ---------------------------------------------------------------------------
# S8: límite de intentos de Supabase Auth visible
# ---------------------------------------------------------------------------

def _auth_responde(monkeypatch, estado: dict, *, status: int) -> None:
    """iniciar_sesion real con un Supabase Auth simulado que responde `status`
    a todo sign-in (429 = límite de pedidos; 400 = credenciales inválidas)."""

    class _Auth:
        def sign_in_with_password(self, credenciales):
            estado["sign_ins"].append((credenciales["email"], credenciales["password"]))
            if status == 429:
                raise AuthApiError("Request rate limit reached", 429, "over_request_rate_limit")
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")

    def _create_client(url, key, options=None):
        cliente = type("Cliente", (), {})()
        cliente.auth = _Auth()
        return cliente

    monkeypatch.setattr(auth_repo, "iniciar_sesion", _INICIAR_SESION_REAL)
    monkeypatch.setattr(auth_repo, "create_client", _create_client)


def test_login_con_limite_de_intentos_da_429(estado, monkeypatch):
    _auth_responde(monkeypatch, estado, status=429)

    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "temporal1"}
    )

    assert respuesta.status_code == 429
    assert respuesta.json() == {"detail": MENSAJE_RATE_LIMIT}
    assert estado["sign_ins"] == [("0f3c@usuarios.local", "temporal1")]


def test_login_con_limite_de_intentos_no_distingue_usernames(estado, monkeypatch):
    """S1+S8: bajo 429 de Supabase, existente, inexistente e inválido responden igual."""
    _auth_responde(monkeypatch, estado, status=429)
    cliente = _cliente(estado)

    existente = cliente.post("/auth/login", json={"username": "jperez", "password": "x12345678"})
    inexistente = cliente.post("/auth/login", json={"username": "nadie", "password": "x12345678"})
    invalido = cliente.post("/auth/login", json={"username": "j perez@x", "password": "x12345678"})
    vacio = cliente.post("/auth/login", json={"username": "", "password": ""})

    respuestas = (existente, inexistente, invalido, vacio)
    assert {r.status_code for r in respuestas} == {429}
    assert all(r.json() == {"detail": MENSAJE_RATE_LIMIT} for r in respuestas)


def test_login_con_credenciales_invalidas_de_auth_sigue_dando_401(estado, monkeypatch):
    _auth_responde(monkeypatch, estado, status=400)

    respuesta = _cliente(estado).post(
        "/auth/login", json={"username": "jperez", "password": "otra-cosa"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}


def test_cambiar_password_con_limite_de_intentos_da_429_y_no_cambia_nada(estado, monkeypatch):
    _auth_responde(monkeypatch, estado, status=429)

    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 429
    assert respuesta.json() == {"detail": MENSAJE_RATE_LIMIT}
    _sin_cambios(estado)


def test_cambiar_password_con_credenciales_invalidas_de_auth_sigue_dando_422(estado, monkeypatch):
    _auth_responde(monkeypatch, estado, status=400)

    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "equivocada", "password_nueva": "definitiva8"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La contraseña actual es incorrecta"}
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


@pytest.mark.parametrize("username", ["jperez", "nadie", "j perez@x", ""])
def test_login_con_password_vacia_da_el_401_generico(estado, monkeypatch, username):
    """S1: con el cliente gotrue real, una password vacía falla antes del HTTP
    (AuthInvalidCredentialsError, no AuthApiError). Tiene que dar el mismo 401
    genérico para cualquier username, nunca un 500."""
    from types import SimpleNamespace

    monkeypatch.setattr(auth_repo, "iniciar_sesion", _INICIAR_SESION_REAL)
    monkeypatch.setattr(
        auth_repo,
        "get_settings",
        lambda: SimpleNamespace(supabase_url="http://127.0.0.1:9", supabase_anon_key="aaa.bbb.ccc"),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    respuesta = TestClient(app, raise_server_exceptions=False).post(
        "/auth/login", json={"username": username, "password": ""}
    )

    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_LOGIN}


# S1+S8 (L8): real gotrue client over httpx.MockTransport, no network.
_USERNAMES_PARIDAD = ["jperez", "JPEREZ", " jperez ", "nadie", "j perez@x", "", "jp", "x" * 31]
_RL = {"code": 429, "error_code": "over_request_rate_limit", "msg": "Request rate limit reached"}
_BAD = {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"}


def _gotrue_real(monkeypatch, *, status=None, body=None, responder=None):
    """Cliente gotrue real sobre httpx.MockTransport. `responder(request)` arma la
    respuesta por ruta (o lanza un error de red); si no, todo responde `status`/`body`."""
    from types import SimpleNamespace

    pedidos = []

    def handler(request):
        pedidos.append(request)
        if responder is not None:
            return responder(request)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(auth_repo, "iniciar_sesion", _INICIAR_SESION_REAL)
    monkeypatch.setattr(
        auth_repo,
        "get_settings",
        lambda: SimpleNamespace(supabase_url="http://auth.test", supabase_anon_key="aaa.bbb.ccc"),
    )
    monkeypatch.setattr(
        auth_repo,
        "build_resilient_httpx_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return pedidos


@pytest.mark.parametrize("status,body", [(400, _BAD), (429, _RL)])
def test_login_password_vacia_401_identico_sin_llamar_a_auth(estado, monkeypatch, status, body):
    """S1, S8: password vacía nunca llega a Auth y da el mismo 401 para todo username."""
    pedidos = _gotrue_real(monkeypatch, status=status, body=body)
    cliente = _cliente(estado)
    respuestas = [
        cliente.post("/auth/login", json={"username": u, "password": ""}) for u in _USERNAMES_PARIDAD
    ]
    assert [(r.status_code, r.json()) for r in respuestas] == [
        (401, {"detail": MENSAJE_LOGIN})
    ] * len(_USERNAMES_PARIDAD)
    assert pedidos == []


@pytest.mark.parametrize("password", ["x12345678", " "])
def test_login_429_real_identico_para_todo_username(estado, monkeypatch, password):
    """S1, S8: con el cliente gotrue real, un 429 de Auth da el mismo 429 para todo username."""
    pedidos = _gotrue_real(monkeypatch, status=429, body=_RL)
    cliente = _cliente(estado)
    respuestas = [
        cliente.post("/auth/login", json={"username": u, "password": password}) for u in _USERNAMES_PARIDAD
    ]
    assert [(r.status_code, r.json()) for r in respuestas] == [
        (429, {"detail": MENSAJE_RATE_LIMIT})
    ] * len(_USERNAMES_PARIDAD)
    assert len(pedidos) == len(_USERNAMES_PARIDAD)


def test_cambiar_password_actual_vacia_da_422_sin_cambios(estado, monkeypatch):
    """S3, S8: password actual vacía da 422 sin llamar a Auth ni tocar el perfil."""
    pedidos = _gotrue_real(monkeypatch, status=429, body=_RL)
    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password", json={"password_actual": "", "password_nueva": "definitiva8"}
    )
    assert (respuesta.status_code, respuesta.json()) == (422, {"detail": "La contraseña actual es incorrecta"})
    assert pedidos == []
    _sin_cambios(estado)


# ---------------------------------------------------------------------------
# S12: Supabase Auth caído o con respuestas no parseables -> 503 / 429 claros
# ---------------------------------------------------------------------------

def _red_caida(request):
    raise httpx.ConnectError("connection refused", request=request)


_CAIDAS = {
    "502": lambda r: httpx.Response(502, text="<html>502 Bad Gateway</html>"),
    "503": lambda r: httpx.Response(503, text="<html>503 Service Unavailable</html>"),
    "504": lambda r: httpx.Response(504, text="<html>504 Gateway Timeout</html>"),
    "500_json": lambda r: httpx.Response(
        500, json={"code": 500, "error_code": "unexpected_failure", "msg": "Internal Server Error"}
    ),
    "500_no_json": lambda r: httpx.Response(500, text="<html>Internal Server Error</html>"),
    "red": _red_caida,
}
_RL_NO_JSON = lambda r: httpx.Response(429, text="Too Many Requests")  # noqa: E731
_NO_DISPONIBLE = (503, {"detail": MENSAJE_AUTH_NO_DISPONIBLE})
_LIMITE = (429, {"detail": MENSAJE_RATE_LIMIT})


@pytest.mark.parametrize(
    "responder,esperado",
    [(r, _NO_DISPONIBLE) for r in _CAIDAS.values()] + [(_RL_NO_JSON, _LIMITE)],
    ids=[*_CAIDAS, "429_no_json"],
)
def test_login_con_auth_caido_responde_igual_para_todo_username(estado, monkeypatch, responder, esperado):
    """S12 + S1: un Auth caído da 503 (o el 429 de S8) para todo username, nunca
    500 ni el 401 de credenciales."""
    pedidos = _gotrue_real(monkeypatch, responder=responder)
    cliente = _cliente(estado)

    respuestas = [
        cliente.post("/auth/login", json={"username": u, "password": "x12345678"})
        for u in _USERNAMES_PARIDAD
    ]

    assert [(r.status_code, r.json()) for r in respuestas] == [esperado] * len(_USERNAMES_PARIDAD)
    assert len(pedidos) == len(_USERNAMES_PARIDAD)


@pytest.mark.parametrize(
    "responder,esperado",
    [(r, _NO_DISPONIBLE) for r in _CAIDAS.values()] + [(_RL_NO_JSON, _LIMITE)],
    ids=[*_CAIDAS, "429_no_json"],
)
def test_cambiar_password_con_auth_caido_no_cambia_nada(estado, monkeypatch, responder, esperado):
    """S12: verificar la contraseña actual con Auth caído da 503 (o 429), nunca
    el 422 de contraseña incorrecta, y no toca nada."""
    _gotrue_real(monkeypatch, responder=responder)

    respuesta = _cliente(estado, sub="id-jperez").post(
        "/auth/cambiar-password",
        json={"password_actual": "temporal1", "password_nueva": "definitiva8"},
    )

    assert (respuesta.status_code, respuesta.json()) == esperado
    _sin_cambios(estado)


# Con el lookup de Auth real (get_user_by_id): el id del usuario tiene que ser un uuid.
_ID_JPEREZ = "5b0c6a1e-3f7d-4c2a-9e8b-1a2b3c4d5e6f"
_RUTA_USUARIO_AUTH = "/auth/v1/admin/users/"


def _usuario_auth(usuario_id: str) -> dict:
    return {
        "id": usuario_id,
        "email": "0f3c@usuarios.local",
        "aud": "authenticated",
        "app_metadata": {},
        "user_metadata": {},
        "created_at": "2026-01-01T00:00:00Z",
    }


def _lookup_auth_real(monkeypatch, estado: dict) -> None:
    """obtener_email_auth real con un service client gotrue sobre el mismo
    MockTransport que instala _gotrue_real (llamar después de _gotrue_real)."""
    from supabase import ClientOptions, create_client

    fila = estado["usuarios"].pop("id-jperez")
    estado["usuarios"][_ID_JPEREZ] = {**fila, "id": _ID_JPEREZ}
    estado["emails"] = {_ID_JPEREZ: "0f3c@usuarios.local"}
    servicio = create_client(
        "http://auth.test",
        "aaa.bbb.ccc",
        options=ClientOptions(httpx_client=auth_repo.build_resilient_httpx_client()),
    )
    monkeypatch.setattr(auth_repo, "obtener_email_auth", _OBTENER_EMAIL_AUTH_REAL)
    monkeypatch.setattr(auth_service, "get_service_client", lambda: servicio)


@pytest.mark.parametrize(
    "falla,esperado",
    [
        (_CAIDAS["502"], _NO_DISPONIBLE),
        (_CAIDAS["500_json"], _NO_DISPONIBLE),
        (_CAIDAS["red"], _NO_DISPONIBLE),
        (_RL_NO_JSON, _LIMITE),
    ],
    ids=["502", "500_json", "red", "429_no_json"],
)
def test_login_con_lookup_de_auth_caido_responde_igual_para_todo_username(
    estado, monkeypatch, falla, esperado
):
    """S12 + S13: si get_user_by_id falla, existente e inexistente dan la misma
    respuesta (también lo intenta el inexistente, con el id ficticio)."""

    def responder(request):
        if request.url.path.startswith(_RUTA_USUARIO_AUTH):
            return falla(request)
        return httpx.Response(400, json=_BAD)

    _gotrue_real(monkeypatch, responder=responder)
    _lookup_auth_real(monkeypatch, estado)
    cliente = _cliente(estado)

    respuestas = [
        cliente.post("/auth/login", json={"username": u, "password": "x12345678"})
        for u in _USERNAMES_PARIDAD
    ]

    assert [(r.status_code, r.json()) for r in respuestas] == [esperado] * len(_USERNAMES_PARIDAD)


# ---------------------------------------------------------------------------
# S13: misma secuencia de llamadas externas para todo username
# ---------------------------------------------------------------------------

def test_login_hace_la_misma_secuencia_de_llamadas_para_todo_username(estado, monkeypatch):
    """S13: lookup de username, lookup en Auth y sign-in para existente,
    inexistente, mal formado y vacío; todos terminan en el mismo 401."""
    import re

    def responder(request):
        if request.url.path.startswith(_RUTA_USUARIO_AUTH):
            usuario_id = request.url.path.removeprefix(_RUTA_USUARIO_AUTH)
            if usuario_id == _ID_JPEREZ:
                return httpx.Response(200, json=_usuario_auth(usuario_id))
            return httpx.Response(
                404, json={"code": 404, "error_code": "user_not_found", "msg": "User not found"}
            )
        return httpx.Response(400, json=_BAD)

    pedidos = _gotrue_real(monkeypatch, responder=responder)
    _lookup_auth_real(monkeypatch, estado)
    cliente = _cliente(estado)
    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    secuencias = {}
    for username in ["jperez", "nadie", "j perez@x", ""]:
        pedidos.clear()
        estado["lookups"].clear()
        respuesta = cliente.post("/auth/login", json={"username": username, "password": "x12345678"})
        assert (respuesta.status_code, respuesta.json()) == (401, {"detail": MENSAJE_LOGIN})
        secuencias[username] = (
            len(estado["lookups"]),
            [(p.method, uuid.sub("{id}", p.url.path)) for p in pedidos],
        )

    esperada = (1, [("GET", "/auth/v1/admin/users/{id}"), ("POST", "/auth/v1/token")])
    assert secuencias == dict.fromkeys(secuencias, esperada)


def _sin_cambios_lookup_real(estado: dict) -> None:
    """_sin_cambios tras _lookup_auth_real (la fila pasa a _ID_JPEREZ)."""
    assert estado["password_updates"] == []
    assert estado["perfil_updates"] == []
    assert estado["usuarios"][_ID_JPEREZ]["debe_cambiar_password"] is True


# S12 (L14 #2): el lookup del email de Auth dentro de /auth/cambiar-password.
@pytest.mark.parametrize(
    "falla,esperado",
    [(r, _NO_DISPONIBLE) for r in _CAIDAS.values()] + [(_RL_NO_JSON, _LIMITE)],
    ids=[*_CAIDAS, "429_no_json"],
)
def test_cambiar_password_con_lookup_de_auth_caido_no_cambia_nada(estado, monkeypatch, falla, esperado):
    def responder(request):
        if request.url.path.startswith(_RUTA_USUARIO_AUTH):
            return falla(request)
        return httpx.Response(200, json={})  # nunca debería llegar al sign-in

    pedidos = _gotrue_real(monkeypatch, responder=responder)
    _lookup_auth_real(monkeypatch, estado)
    respuesta = _cliente(estado, sub=_ID_JPEREZ).post(
        "/auth/cambiar-password", json={"password_actual": "temporal1", "password_nueva": "definitiva8"}
    )
    assert (respuesta.status_code, respuesta.json()) == esperado
    assert [p for p in pedidos if p.url.path == "/auth/v1/token"] == []
    _sin_cambios_lookup_real(estado)


def test_cambiar_password_sin_cuenta_auth_da_422(estado, monkeypatch):
    def responder(request):
        if request.url.path.startswith(_RUTA_USUARIO_AUTH):
            return httpx.Response(404, json={"code": 404, "error_code": "user_not_found", "msg": "User not found"})
        return httpx.Response(400, json=_BAD)

    _gotrue_real(monkeypatch, responder=responder)
    _lookup_auth_real(monkeypatch, estado)
    respuesta = _cliente(estado, sub=_ID_JPEREZ).post(
        "/auth/cambiar-password", json={"password_actual": "temporal1", "password_nueva": "definitiva8"}
    )
    assert (respuesta.status_code, respuesta.json()) == (422, {"detail": "La contraseña actual es incorrecta"})
    _sin_cambios_lookup_real(estado)


def test_login_solo_la_cuenta_real_obtiene_sesion_aunque_auth_acepte_el_placeholder(estado, monkeypatch):
    """S13: aunque Auth emitiera sesión para el email ficticio, solo la cuenta real entra."""

    def responder(request):
        if request.url.path.startswith(_RUTA_USUARIO_AUTH):
            uid = request.url.path.removeprefix(_RUTA_USUARIO_AUTH)
            if uid == _ID_JPEREZ:
                return httpx.Response(200, json=_usuario_auth(uid))
            return httpx.Response(404, json={"code": 404, "error_code": "user_not_found", "msg": "User not found"})
        return httpx.Response(
            200,
            json={
                "access_token": "acc",
                "refresh_token": "ref",
                "expires_in": 3600,
                "expires_at": 1_900_000_000,
                "token_type": "bearer",
                "user": _usuario_auth(_ID_JPEREZ),
            },
        )

    _gotrue_real(monkeypatch, responder=responder)
    _lookup_auth_real(monkeypatch, estado)
    cliente = _cliente(estado)
    for username in _USERNAMES_PARIDAD + ["login inexistente", "login-inexistente"]:
        r = cliente.post("/auth/login", json={"username": username, "password": "x12345678"})
        if username.strip().lower() == "jperez":
            assert r.status_code == 200 and "@" not in r.text, username
        else:
            assert (r.status_code, r.json()) == (401, {"detail": MENSAJE_LOGIN}), username
