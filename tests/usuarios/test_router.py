"""tests/usuarios/test_router.py -- autorización de /usuarios por rol
(odd/tasks/roles-permisos-matriz.md, S7). Tests unitarios: el usuario se inyecta
con dependency_overrides y el repositorio se reemplaza por un almacén en memoria,
así corren sin Supabase."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios import service
from services.presupuestacion.usuarios.router import router
from services.shared.exceptions import register_exception_handlers

DROGUERIA = "d-propia"
OTRA_DROGUERIA = "d-otra"


def _fila(usuario_id: str, rol: str, drogueria_id: str | None = DROGUERIA) -> dict:
    return {
        "id": usuario_id,
        "drogueria_id": drogueria_id,
        "rol": rol,
        "nombre": usuario_id,
        "apellido": None,
        "es_sistema": rol == "sistema",
        "activo": True,
    }


@pytest.fixture
def almacen(monkeypatch) -> dict[str, dict]:
    filas = {
        "yo": _fila("yo", "gerencia"),
        "admin-propio": _fila("admin-propio", "admin"),
        "gerencia-propio": _fila("gerencia-propio", "gerencia"),
        "lider-propio": _fila("lider-propio", "lider_comercial"),
        "comercial-propio": _fila("comercial-propio", "comercial"),
        "compras-propio": _fila("compras-propio", "compras"),
        "comercial-otra": _fila("comercial-otra", "comercial", OTRA_DROGUERIA),
        "superadmin": _fila("superadmin", "superadmin", None),
        "sistema": _fila("sistema", "sistema"),
    }

    def _crear_perfil(client, fila):
        filas[fila["id"]] = {**fila, "activo": True}
        return filas[fila["id"]]

    def _actualizar(usuario_id, **campos):
        filas[usuario_id] = {**filas[usuario_id], **campos}
        return filas[usuario_id]

    monkeypatch.setattr(service, "get_service_client", lambda: None)
    monkeypatch.setattr(repo, "invitar_usuario_auth", lambda client, **kw: "nuevo")
    monkeypatch.setattr(repo, "crear_perfil_usuario", _crear_perfil)
    monkeypatch.setattr(repo, "obtener_usuario", lambda client, *, usuario_id: filas.get(usuario_id))
    monkeypatch.setattr(
        repo, "actualizar_rol", lambda client, *, usuario_id, rol: _actualizar(usuario_id, rol=rol)
    )
    monkeypatch.setattr(
        repo,
        "actualizar_activo",
        lambda client, *, usuario_id, activo: _actualizar(usuario_id, activo=activo),
    )
    monkeypatch.setattr(
        repo, "eliminar_usuario_auth", lambda client, *, usuario_id: filas.pop(usuario_id)
    )
    return filas


def _cliente(rol: str, usuario_id: str = "yo", drogueria_id: str | None = DROGUERIA) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id=usuario_id, drogueria_id=drogueria_id, rol=rol
    )
    return TestClient(app)


def _body_crear(rol: str) -> dict:
    return {
        "email": "nuevo@seed.local",
        "nombre": "Nuevo",
        "apellido": "Usuario",
        "rol": rol,
        "drogueria_id": OTRA_DROGUERIA,
    }


ROLES_INFERIORES = ("gerencia", "lider_comercial", "comercial", "compras")


# ---------------------------------------------------------------------------
# S7: gerencia gestiona usuarios de roles inferiores en su droguería
# ---------------------------------------------------------------------------

def test_gerencia_lista_usuarios():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="yo", drogueria_id=DROGUERIA, rol="gerencia"
    )

    class _Consulta:
        def __getattr__(self, _nombre):
            return lambda *a, **kw: self

        @property
        def data(self):
            return [_fila("yo", "gerencia")]

    class _UserClient:
        def table(self, _nombre):
            return _Consulta()

    app.dependency_overrides[get_user_client] = lambda: _UserClient()

    respuesta = TestClient(app).get("/usuarios")

    assert respuesta.status_code == 200
    assert [u["id"] for u in respuesta.json()] == ["yo"]


@pytest.mark.parametrize("rol", ROLES_INFERIORES)
def test_gerencia_invita_rol_inferior_en_su_drogueria(almacen, rol):
    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear(rol))

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == rol
    # la droguería se fuerza a la del creador, igual que para admin
    assert respuesta.json()["drogueria_id"] == DROGUERIA


@pytest.mark.parametrize("rol", ["admin", "superadmin"])
def test_gerencia_no_puede_invitar_admin_ni_superadmin(almacen, rol):
    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear(rol))

    assert respuesta.status_code == 403
    assert "nuevo" not in almacen


@pytest.mark.parametrize("objetivo", ["gerencia-propio", "lider-propio", "comercial-propio", "compras-propio"])
def test_gerencia_cambia_rol_de_rol_inferior_de_su_drogueria(almacen, objetivo):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/rol", json={"rol": "compras"})

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "compras"


def test_gerencia_no_puede_asignar_admin(almacen):
    respuesta = _cliente("gerencia").patch("/usuarios/comercial-propio/rol", json={"rol": "admin"})

    assert respuesta.status_code == 403
    assert almacen["comercial-propio"]["rol"] == "comercial"


@pytest.mark.parametrize(
    ("objetivo", "rol_original"),
    [("admin-propio", "admin"), ("comercial-otra", "comercial"), ("superadmin", "superadmin"), ("sistema", "sistema"), ("yo", "gerencia")],
)
def test_gerencia_no_puede_cambiar_rol_de_admin_otra_drogueria_protegidos_ni_propio(
    almacen, objetivo, rol_original
):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/rol", json={"rol": "compras"})

    assert respuesta.status_code == 403
    assert almacen[objetivo]["rol"] == rol_original


@pytest.mark.parametrize("objetivo", ["gerencia-propio", "lider-propio", "comercial-propio", "compras-propio"])
def test_gerencia_desactiva_rol_inferior_de_su_drogueria(almacen, objetivo):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/activo", json={"activo": False})

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False


@pytest.mark.parametrize("objetivo", ["admin-propio", "comercial-otra", "superadmin", "sistema", "yo"])
def test_gerencia_no_puede_desactivar_admin_otra_drogueria_protegidos_ni_propio(almacen, objetivo):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/activo", json={"activo": False})

    assert respuesta.status_code == 403
    assert almacen[objetivo]["activo"] is True


@pytest.mark.parametrize("objetivo", ["gerencia-propio", "lider-propio", "comercial-propio", "compras-propio"])
def test_gerencia_elimina_rol_inferior_de_su_drogueria(almacen, objetivo):
    respuesta = _cliente("gerencia").delete(f"/usuarios/{objetivo}")

    assert respuesta.status_code == 204
    assert objetivo not in almacen


@pytest.mark.parametrize("objetivo", ["admin-propio", "comercial-otra", "superadmin", "sistema", "yo"])
def test_gerencia_no_puede_eliminar_admin_otra_drogueria_protegidos_ni_propio(almacen, objetivo):
    respuesta = _cliente("gerencia").delete(f"/usuarios/{objetivo}")

    assert respuesta.status_code == 403
    assert objetivo in almacen


# ---------------------------------------------------------------------------
# Preservación: admin, superadmin y el resto de los roles quedan igual
# ---------------------------------------------------------------------------

def test_admin_sigue_modificando_admin_de_su_drogueria(almacen):
    respuesta = _cliente("admin", usuario_id="admin-yo").patch(
        "/usuarios/admin-propio/rol", json={"rol": "gerencia"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "gerencia"


def test_admin_sigue_invitando_en_su_drogueria(almacen):
    respuesta = _cliente("admin", usuario_id="admin-yo").post("/usuarios", json=_body_crear("comercial"))

    assert respuesta.status_code == 200
    assert respuesta.json()["drogueria_id"] == DROGUERIA


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "mensaje"),
    [
        ("patch", "/usuarios/comercial-otra/rol", {"rol": "compras"}, "Un admin solo puede modificar usuarios de su droguería"),
        ("patch", "/usuarios/comercial-otra/activo", {"activo": False}, "Un admin solo puede modificar usuarios de su droguería"),
        ("delete", "/usuarios/comercial-otra", None, "Un admin solo puede eliminar usuarios de su droguería"),
    ],
)
def test_admin_sigue_recibiendo_el_mismo_mensaje_fuera_de_su_drogueria(almacen, metodo, ruta, cuerpo, mensaje):
    cliente = _cliente("admin", usuario_id="admin-yo")
    respuesta = cliente.request(metodo.upper(), ruta, json=cuerpo)

    assert respuesta.status_code == 403
    assert mensaje in respuesta.text
    assert almacen["comercial-otra"] == _fila("comercial-otra", "comercial", OTRA_DROGUERIA)


def test_admin_sigue_sin_poder_asignar_admin(almacen):
    respuesta = _cliente("admin", usuario_id="admin-yo").patch(
        "/usuarios/comercial-propio/rol", json={"rol": "admin"}
    )

    assert respuesta.status_code == 403
    assert almacen["comercial-propio"]["rol"] == "comercial"


def test_superadmin_sigue_asignando_admin(almacen):
    respuesta = _cliente("superadmin", usuario_id="superadmin", drogueria_id=None).patch(
        "/usuarios/comercial-otra/rol", json={"rol": "admin"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "admin"


@pytest.mark.parametrize("rol", ["lider_comercial", "comercial", "compras"])
def test_roles_sin_gestion_siguen_rechazados(almacen, rol):
    cliente = _cliente(rol)

    assert cliente.post("/usuarios", json=_body_crear("comercial")).status_code == 403
    assert cliente.patch("/usuarios/compras-propio/rol", json={"rol": "comercial"}).status_code == 403
    assert cliente.patch("/usuarios/compras-propio/activo", json={"activo": False}).status_code == 403
    assert cliente.delete("/usuarios/compras-propio").status_code == 403
    assert almacen["compras-propio"] == _fila("compras-propio", "compras")
