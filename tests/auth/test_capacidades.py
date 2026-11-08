"""GET /auth/capacidades -- capacidades del rol del usuario para el frontend
(odd/tasks/roles-capacidades.md S4)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.auth.router import router
from services.shared.auth import UserClaims, UsuarioPerfil, get_current_claims, get_current_user
from services.shared.database import get_user_client
from services.shared.exceptions import register_exception_handlers
from services.shared.permisos import capacidades_de


def _client(override) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    override(app)
    return TestClient(app)


def _como(rol: str):
    def _override(app: FastAPI) -> None:
        app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(id="u", drogueria_id="d", rol=rol)

    return _override


def test_devuelve_las_capacidades_ordenadas_del_rol():
    respuesta = _client(_como("compras")).get("/auth/capacidades")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"rol": "compras", "capacidades": capacidades_de("compras")}
    assert "pcp.escribir" in respuesta.json()["capacidades"]
    assert "presupuestos.importar_legacy" not in respuesta.json()["capacidades"]


def test_rol_sin_capacidades_devuelve_lista_vacia():
    respuesta = _client(_como("sistema")).get("/auth/capacidades")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"rol": "sistema", "capacidades": []}


def test_con_cambio_de_password_pendiente_queda_bloqueado():
    class _UserClient:
        def table(self, _nombre):
            class _Consulta:
                def __getattr__(self, _metodo):
                    return lambda *_a, **_k: self

                def execute(self):
                    class _R:
                        data = [
                            {
                                "id": "u",
                                "drogueria_id": "d",
                                "rol": "admin",
                                "activo": True,
                                "debe_cambiar_password": True,
                            }
                        ]

                    return _R()

            return _Consulta()

    def _override(app: FastAPI) -> None:
        app.dependency_overrides[get_current_claims] = lambda: UserClaims(sub="u", exp=0)
        app.dependency_overrides[get_user_client] = lambda: _UserClient()

    respuesta = _client(_override).get("/auth/capacidades")
    assert respuesta.status_code == 403
    assert "Debés cambiar tu contraseña antes de continuar" in respuesta.text
