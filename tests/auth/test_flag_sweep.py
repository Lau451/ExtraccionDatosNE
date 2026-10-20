"""tests/auth/test_flag_sweep.py -- barrido de regresión del bloqueo por cambio de
contraseña pendiente (odd/tasks/login-usuario-alta-admin.md S3, S10a).

Recorre TODAS las rutas de las apps reales (presupuestacion y extraccion) con un
usuario con debe_cambiar_password = true: cada una responde 403 con el mensaje
del bloqueo, salvo las tres permitidas. Unitario: get_current_claims y
get_user_client se reemplazan por fakes; FastAPI resuelve las dependencias antes
de validar el body, así que no hace falta mandar uno válido. Una ruta nueva que
olvide get_current_user/require_roles rompe este test.
"""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from services.extraccion.main import app as app_extraccion
from services.presupuestacion.main import app as app_presupuestacion
from services.shared.auth import MENSAJE_CAMBIO_PASSWORD_PENDIENTE, UserClaims, get_current_claims
from services.shared.database import get_user_client

USUARIO_ID = "u-flag"
OTRO_ID = "00000000-0000-0000-0000-000000000001"

# Las únicas salidas del bloqueo (S3). GET /usuarios/{usuario_id} solo con el
# propio id; con otro id sí se bloquea (ver test de abajo).
PERMITIDAS = {
    ("POST", "/auth/login"),
    ("POST", "/auth/cambiar-password"),
    ("GET", "/usuarios/{usuario_id}"),
}

_PARAMETRO_DE_RUTA = re.compile(r"\{[^}]+\}")


class _UserClient:
    """Responde cualquier lectura de `usuarios` con el perfil bloqueado."""

    def table(self, _nombre):
        class _Consulta:
            def __getattr__(self, _metodo):
                return lambda *_a, **_k: self

            def execute(self):
                class _R:
                    data = [
                        {
                            "id": USUARIO_ID,
                            "drogueria_id": "d-1",
                            "rol": "admin",
                            "nombre": "Bloqueado",
                            "apellido": None,
                            "es_sistema": False,
                            "activo": True,
                            "username": "bloqueado",
                            "debe_cambiar_password": True,
                        }
                    ]

                return _R()

        return _Consulta()


def _rutas(app):
    for ruta in app.routes:
        if not isinstance(ruta, APIRoute):
            continue
        for metodo in sorted(ruta.methods - {"HEAD", "OPTIONS"}):
            yield metodo, ruta.path


CASOS = [
    pytest.param(app, metodo, ruta, id=f"{nombre} {metodo} {ruta}")
    for nombre, app in (("presupuestacion", app_presupuestacion), ("extraccion", app_extraccion))
    for metodo, ruta in _rutas(app)
    if (metodo, ruta) not in PERMITIDAS
]


@pytest.fixture
def cliente_bloqueado():
    def _crear(app) -> TestClient:
        app.dependency_overrides[get_current_claims] = lambda: UserClaims(sub=USUARIO_ID, exp=0)
        app.dependency_overrides[get_user_client] = lambda: _UserClient()
        return TestClient(app, raise_server_exceptions=False)

    yield _crear
    for app in (app_presupuestacion, app_extraccion):
        app.dependency_overrides.clear()


def test_el_barrido_cubre_ambas_apps():
    apps = {caso.values[0] for caso in CASOS}
    assert apps == {app_presupuestacion, app_extraccion}


@pytest.mark.parametrize(("app", "metodo", "ruta"), CASOS)
def test_usuario_con_password_pendiente_recibe_403_en_toda_ruta(cliente_bloqueado, app, metodo, ruta):
    respuesta = cliente_bloqueado(app).request(metodo, _PARAMETRO_DE_RUTA.sub(OTRO_ID, ruta))

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_CAMBIO_PASSWORD_PENDIENTE}


def test_usuario_con_password_pendiente_no_lee_el_perfil_de_otro(cliente_bloqueado):
    respuesta = cliente_bloqueado(app_presupuestacion).get(f"/usuarios/{OTRO_ID}")

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": MENSAJE_CAMBIO_PASSWORD_PENDIENTE}


def test_usuario_con_password_pendiente_lee_su_propio_perfil(cliente_bloqueado):
    respuesta = cliente_bloqueado(app_presupuestacion).get(f"/usuarios/{USUARIO_ID}")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == USUARIO_ID
