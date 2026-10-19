"""tests/shared/test_auth.py -- bloqueo por cambio de contraseña pendiente
(odd/tasks/login-usuario-alta-admin.md S3). Unitarios: se reemplazan solo las
claims y el cliente de Supabase; get_current_user y la dependencia permisiva son
las reales, ejercitadas a través de endpoints HTTP."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services.shared import auth as shared_auth
from services.shared.auth import UserClaims, UsuarioPerfil, get_current_claims, get_current_user
from services.shared.database import get_user_client
from services.shared.exceptions import register_exception_handlers
from services.presupuestacion.usuarios import repository as usuarios_repo
from services.presupuestacion.usuarios import service as usuarios_service
from services.presupuestacion.usuarios.router import router as usuarios_router

MENSAJE_PENDIENTE = "Debés cambiar tu contraseña antes de continuar"


def _fila(usuario_id: str, *, debe_cambiar_password: bool, activo: bool = True) -> dict:
    return {
        "id": usuario_id,
        "drogueria_id": "d-propia",
        "rol": "comercial",
        "nombre": usuario_id,
        "apellido": None,
        "es_sistema": False,
        "activo": activo,
        "username": usuario_id,
        "debe_cambiar_password": debe_cambiar_password,
    }


class _Consulta:
    def __init__(self, filas: dict[str, dict]) -> None:
        self._filas = filas
        self._id: str | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def eq(self, columna, valor):
        assert columna == "id"
        self._id = valor
        return self

    def execute(self):
        class _Resultado:
            pass

        resultado = _Resultado()
        if self._id is None:
            resultado.data = list(self._filas.values())
        else:
            resultado.data = [self._filas[self._id]] if self._id in self._filas else []
        return resultado


class _UserClient:
    def __init__(self, filas: dict[str, dict]) -> None:
        self._filas = filas

    def table(self, nombre):
        assert nombre == "usuarios"
        return _Consulta(self._filas)


@pytest.fixture
def filas() -> dict[str, dict]:
    return {
        "pendiente": _fila("pendiente", debe_cambiar_password=True),
        "al-dia": _fila("al-dia", debe_cambiar_password=False),
        "inactivo": _fila("inactivo", debe_cambiar_password=False, activo=False),
    }


def _app(filas: dict[str, dict], sub: str) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(usuarios_router)

    @app.get("/otro-modulo")
    def _otro_modulo(usuario: UsuarioPerfil = Depends(get_current_user)) -> dict:
        return {"id": usuario.id, "debe_cambiar_password": usuario.debe_cambiar_password}

    app.dependency_overrides[get_current_claims] = lambda: UserClaims(sub=sub, exp=0)
    app.dependency_overrides[get_user_client] = lambda: _UserClient(filas)
    return TestClient(app)


def test_usuario_con_cambio_pendiente_recibe_403_en_endpoint_normal(filas):
    respuesta = _app(filas, "pendiente").get("/otro-modulo")

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_PENDIENTE}


def test_usuario_con_cambio_pendiente_recibe_403_al_listar_usuarios(filas):
    respuesta = _app(filas, "pendiente").get("/usuarios")

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_PENDIENTE}


def test_usuario_con_cambio_pendiente_no_edita_su_perfil(filas, monkeypatch):
    llamadas = []
    monkeypatch.setattr(usuarios_service, "get_service_client", lambda: None)
    monkeypatch.setattr(
        usuarios_repo, "actualizar_perfil", lambda client, **kw: llamadas.append(kw)
    )

    respuesta = _app(filas, "pendiente").patch("/usuarios/me", json={"nombre": "Otro"})

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_PENDIENTE}
    assert llamadas == []
    assert filas["pendiente"]["nombre"] == "pendiente"


def test_usuario_con_cambio_pendiente_lee_su_propio_perfil(filas):
    respuesta = _app(filas, "pendiente").get("/usuarios/pendiente")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == "pendiente"
    assert respuesta.json()["debe_cambiar_password"] is True
    assert respuesta.json()["username"] == "pendiente"


def test_usuario_con_cambio_pendiente_no_lee_perfil_ajeno(filas):
    respuesta = _app(filas, "pendiente").get("/usuarios/al-dia")

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_PENDIENTE}


def test_usuario_al_dia_sigue_accediendo_a_otros_modulos(filas):
    respuesta = _app(filas, "al-dia").get("/otro-modulo")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": "al-dia", "debe_cambiar_password": False}


def test_usuario_al_dia_sigue_leyendo_perfil_ajeno(filas):
    respuesta = _app(filas, "al-dia").get("/usuarios/pendiente")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == "pendiente"


def test_usuario_desactivado_sigue_recibiendo_401(filas):
    cliente = _app(filas, "inactivo")

    for ruta in ("/otro-modulo", "/usuarios/inactivo"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 401
        assert respuesta.json() == {"detail": "Usuario desactivado"}


def test_perfil_sin_el_campo_queda_sin_cambio_pendiente():
    # Otros módulos construyen UsuarioPerfil sin conocer el flag.
    perfil = UsuarioPerfil(id="x", drogueria_id=None, rol="superadmin")

    assert perfil.debe_cambiar_password is False


def test_mensaje_de_cambio_pendiente_es_el_del_contrato():
    assert shared_auth.MENSAJE_CAMBIO_PASSWORD_PENDIENTE == MENSAJE_PENDIENTE
