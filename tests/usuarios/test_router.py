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
        "username": usuario_id,
        "debe_cambiar_password": False,
    }


@pytest.fixture
def auth_admin() -> dict[str, list]:
    """Registro de llamadas a Supabase Auth admin (create/update/delete)."""
    return {"creados": [], "passwords": [], "borrados": []}


@pytest.fixture
def almacen(monkeypatch, auth_admin) -> dict[str, dict]:
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

    def _crear_usuario_auth(client, *, email, password, nombre, apellido, rol):
        auth_admin["creados"].append({"email": email, "password": password})
        return "nuevo"

    def _por_username(client, *, username):
        return next((f for f in filas.values() if f["username"] == username), None)

    def _actualizar(usuario_id, **campos):
        filas[usuario_id] = {**filas[usuario_id], **campos}
        return filas[usuario_id]

    monkeypatch.setattr(service, "get_service_client", lambda: None)
    monkeypatch.setattr(repo, "crear_usuario_auth", _crear_usuario_auth)
    monkeypatch.setattr(repo, "obtener_usuario_por_username", _por_username)
    monkeypatch.setattr(
        repo,
        "actualizar_password_auth",
        lambda client, *, usuario_id, password: auth_admin["passwords"].append((usuario_id, password)),
    )
    monkeypatch.setattr(
        repo,
        "actualizar_perfil",
        lambda client, *, usuario_id, campos: _actualizar(usuario_id, **campos),
    )
    monkeypatch.setattr(
        repo,
        "descartar_usuario_auth",
        lambda client, *, usuario_id: auth_admin["borrados"].append(usuario_id),
    )
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


def _cliente(
    rol: str,
    usuario_id: str = "yo",
    drogueria_id: str | None = DROGUERIA,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id=usuario_id, drogueria_id=drogueria_id, rol=rol
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _body_crear(rol: str) -> dict:
    return {
        "username": "nuevo.usuario",
        "password": "temporal1",
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
def test_gerencia_no_puede_invitar_admin_ni_superadmin(almacen, auth_admin, rol):
    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear(rol))

    assert respuesta.status_code == 403
    assert "nuevo" not in almacen
    assert auth_admin["creados"] == []


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


# ---------------------------------------------------------------------------
# S2: alta con username + contraseña temporal (sin invitación por email)
# ---------------------------------------------------------------------------

def test_alta_crea_cuenta_auth_con_email_interno_opaco_y_flag_pendiente(almacen, auth_admin):
    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear("comercial"))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["username"] == "nuevo.usuario"
    assert cuerpo["debe_cambiar_password"] is True
    assert almacen["nuevo"]["username"] == "nuevo.usuario"
    assert almacen["nuevo"]["debe_cambiar_password"] is True
    [creado] = auth_admin["creados"]
    assert creado["password"] == "temporal1"
    local, _, dominio = creado["email"].partition("@")
    # opaco: no deriva del username
    assert "nuevo" not in local and len(local) == 32
    assert dominio == service.get_settings().auth_email_domain


def test_alta_guarda_el_username_en_minusculas(almacen):
    body = {**_body_crear("comercial"), "username": "Nuevo.Usuario"}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 200
    assert respuesta.json()["username"] == "nuevo.usuario"


@pytest.mark.parametrize("username", ["abc", "a" * 30, "j.perez_2-x"])
def test_alta_acepta_usernames_en_el_limite_del_formato(almacen, username):
    body = {**_body_crear("comercial"), "username": username}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 200
    assert respuesta.json()["username"] == username


@pytest.mark.parametrize("username", ["ab", "a" * 31, "j perez", "jperez@mail", "ñandu"])
def test_alta_rechaza_username_de_formato_invalido(almacen, auth_admin, username):
    body = {**_body_crear("comercial"), "username": username}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": "El nombre de usuario debe tener entre 3 y 30 caracteres: letras, números, "
        "punto, guion o guion bajo"
    }
    assert auth_admin["creados"] == []
    assert "nuevo" not in almacen


def test_alta_acepta_password_de_8_caracteres(almacen, auth_admin):
    body = {**_body_crear("comercial"), "password": "12345678"}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 200
    assert auth_admin["creados"][0]["password"] == "12345678"


def test_alta_rechaza_password_de_7_caracteres(almacen, auth_admin):
    body = {**_body_crear("comercial"), "password": "1234567"}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La contraseña debe tener al menos 8 caracteres"}
    assert auth_admin["creados"] == []
    assert "nuevo" not in almacen


@pytest.mark.parametrize("username", ["comercial-propio", "Comercial-Propio"])
def test_alta_con_username_repetido_da_409(almacen, auth_admin, username):
    body = {**_body_crear("comercial"), "username": username}

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "Ya existe un usuario con ese nombre de usuario"}
    assert auth_admin["creados"] == []
    assert "nuevo" not in almacen


def test_alta_borra_la_cuenta_auth_si_falla_el_perfil(almacen, auth_admin, monkeypatch):
    def _falla(client, fila):
        raise RuntimeError("insert falló")

    monkeypatch.setattr(repo, "crear_perfil_usuario", _falla)

    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear("comercial"))

    assert respuesta.status_code == 500
    assert len(auth_admin["creados"]) == 1
    assert auth_admin["borrados"] == ["nuevo"]
    assert "nuevo" not in almacen


def test_alta_username_repetido_detectado_al_insertar_da_409_y_compensa(almacen, auth_admin, monkeypatch):
    from postgrest.exceptions import APIError

    def _unique_violation(client, fila):
        raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})

    monkeypatch.setattr(repo, "crear_perfil_usuario", _unique_violation)

    respuesta = _cliente("gerencia").post("/usuarios", json=_body_crear("comercial"))

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "Ya existe un usuario con ese nombre de usuario"}
    assert auth_admin["borrados"] == ["nuevo"]


def test_alta_sin_password_es_rechazada(almacen, auth_admin):
    body = _body_crear("comercial")
    del body["password"]

    respuesta = _cliente("gerencia").post("/usuarios", json=body)

    assert respuesta.status_code == 422
    assert auth_admin["creados"] == []


# ---------------------------------------------------------------------------
# S4: blanqueo de contraseña por el admin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("objetivo", ["gerencia-propio", "lider-propio", "comercial-propio", "compras-propio"])
def test_gerencia_blanquea_password_de_rol_inferior_de_su_drogueria(almacen, auth_admin, objetivo):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/password", json={"password": "temporal2"})

    assert respuesta.status_code == 200
    assert respuesta.json()["debe_cambiar_password"] is True
    assert almacen[objetivo]["debe_cambiar_password"] is True
    assert auth_admin["passwords"] == [(objetivo, "temporal2")]


@pytest.mark.parametrize(
    ("objetivo", "mensaje"),
    [
        ("yo", "No podés blanquear tu propia contraseña"),
        ("superadmin", "No se puede blanquear la contraseña de un superadmin o sistema por esta vía"),
        ("sistema", "No se puede blanquear la contraseña de un superadmin o sistema por esta vía"),
        ("admin-propio", "Gerencia solo puede gestionar usuarios de roles inferiores a admin"),
        ("comercial-otra", "Gerencia solo puede modificar usuarios de su droguería"),
    ],
)
def test_gerencia_no_blanquea_propia_protegidos_admin_ni_otra_drogueria(almacen, auth_admin, objetivo, mensaje):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/password", json={"password": "temporal2"})

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": mensaje}
    assert auth_admin["passwords"] == []
    assert almacen[objetivo]["debe_cambiar_password"] is False


def test_admin_blanquea_admin_de_su_drogueria(almacen, auth_admin):
    respuesta = _cliente("admin", usuario_id="admin-yo").patch(
        "/usuarios/admin-propio/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 200
    assert auth_admin["passwords"] == [("admin-propio", "temporal2")]


def test_admin_no_blanquea_otra_drogueria(almacen, auth_admin):
    respuesta = _cliente("admin", usuario_id="admin-yo").patch(
        "/usuarios/comercial-otra/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Un admin solo puede modificar usuarios de su droguería"}
    assert auth_admin["passwords"] == []


def test_superadmin_blanquea_en_cualquier_drogueria(almacen, auth_admin):
    respuesta = _cliente("superadmin", usuario_id="superadmin", drogueria_id=None).patch(
        "/usuarios/comercial-otra/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 200
    assert almacen["comercial-otra"]["debe_cambiar_password"] is True


def test_blanqueo_rechaza_password_de_7_caracteres(almacen, auth_admin):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/password", json={"password": "1234567"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "La contraseña debe tener al menos 8 caracteres"}
    assert auth_admin["passwords"] == []
    assert almacen["comercial-propio"]["debe_cambiar_password"] is False


def test_blanqueo_acepta_password_de_8_caracteres(almacen, auth_admin):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/password", json={"password": "12345678"}
    )

    assert respuesta.status_code == 200
    assert auth_admin["passwords"] == [("comercial-propio", "12345678")]


def test_blanqueo_usuario_inexistente_da_404(almacen, auth_admin):
    respuesta = _cliente("gerencia").patch("/usuarios/no-existe/password", json={"password": "temporal2"})

    assert respuesta.status_code == 404
    assert auth_admin["passwords"] == []


# ---------------------------------------------------------------------------
# S9: blanqueo atómico (flag antes que Auth, se restaura si Auth falla)
# ---------------------------------------------------------------------------

def test_blanqueo_marca_el_flag_antes_de_cambiar_la_password_en_auth(almacen, auth_admin, monkeypatch):
    flag_al_cambiar_auth = []

    def _actualizar_password(client, *, usuario_id, password):
        flag_al_cambiar_auth.append(almacen[usuario_id]["debe_cambiar_password"])
        auth_admin["passwords"].append((usuario_id, password))

    monkeypatch.setattr(repo, "actualizar_password_auth", _actualizar_password)

    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["debe_cambiar_password"] is True
    assert flag_al_cambiar_auth == [True]
    assert almacen["comercial-propio"]["debe_cambiar_password"] is True
    assert auth_admin["passwords"] == [("comercial-propio", "temporal2")]


@pytest.mark.parametrize("flag_previo", [False, True])
def test_blanqueo_con_auth_fallida_restaura_el_flag_y_devuelve_el_error(
    almacen, auth_admin, monkeypatch, flag_previo
):
    almacen["comercial-propio"]["debe_cambiar_password"] = flag_previo

    def _auth_falla(client, *, usuario_id, password):
        raise service.ValidationError("No se pudo cambiar la contraseña: Auth no disponible")

    monkeypatch.setattr(repo, "actualizar_password_auth", _auth_falla)

    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": "No se pudo cambiar la contraseña: Auth no disponible"}
    assert almacen["comercial-propio"]["debe_cambiar_password"] is flag_previo


def test_blanqueo_si_falla_la_restauracion_el_flag_queda_true(almacen, auth_admin, monkeypatch):
    """S9: si Auth falla y también falla restaurar el flag, la cuenta queda con
    el cambio forzado pendiente (falla cerrado) y el pedido da 500."""
    almacen["comercial-propio"]["debe_cambiar_password"] = False
    original = repo.actualizar_perfil
    llamadas = []

    def _perfil(client, *, usuario_id, campos):
        llamadas.append(campos)
        if len(llamadas) == 2:
            raise RuntimeError("db caída")
        return original(client, usuario_id=usuario_id, campos=campos)

    def _auth_falla(client, *, usuario_id, password):
        raise service.ValidationError("No se pudo cambiar la contraseña: Auth no disponible")

    monkeypatch.setattr(repo, "actualizar_perfil", _perfil)
    monkeypatch.setattr(repo, "actualizar_password_auth", _auth_falla)

    respuesta = _cliente("gerencia", raise_server_exceptions=False).patch(
        "/usuarios/comercial-propio/password", json={"password": "temporal2"}
    )

    assert respuesta.status_code == 500
    assert llamadas == [{"debe_cambiar_password": True}, {"debe_cambiar_password": False}]
    assert almacen["comercial-propio"]["debe_cambiar_password"] is True


# ---------------------------------------------------------------------------
# S5: edición de username por el admin
# ---------------------------------------------------------------------------

def test_gerencia_edita_username_de_rol_inferior_de_su_drogueria(almacen):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/username", json={"username": "J.Perez"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["username"] == "j.perez"
    assert almacen["comercial-propio"]["username"] == "j.perez"


def test_editar_username_al_mismo_valor_no_choca_consigo_mismo(almacen):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/username", json={"username": "comercial-propio"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["username"] == "comercial-propio"


def test_editar_username_repetido_da_409(almacen):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/username", json={"username": "Compras-Propio"}
    )

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "Ya existe un usuario con ese nombre de usuario"}
    assert almacen["comercial-propio"]["username"] == "comercial-propio"


def test_editar_username_de_formato_invalido_da_422(almacen):
    respuesta = _cliente("gerencia").patch(
        "/usuarios/comercial-propio/username", json={"username": "ab"}
    )

    assert respuesta.status_code == 422
    assert almacen["comercial-propio"]["username"] == "comercial-propio"


@pytest.mark.parametrize(
    ("objetivo", "mensaje"),
    [
        ("yo", "No podés cambiar tu propio nombre de usuario"),
        ("superadmin", "No se puede cambiar el nombre de usuario de un superadmin o sistema por esta vía"),
        ("sistema", "No se puede cambiar el nombre de usuario de un superadmin o sistema por esta vía"),
        ("admin-propio", "Gerencia solo puede gestionar usuarios de roles inferiores a admin"),
        ("comercial-otra", "Gerencia solo puede modificar usuarios de su droguería"),
    ],
)
def test_gerencia_no_edita_username_propio_protegidos_admin_ni_otra_drogueria(almacen, objetivo, mensaje):
    respuesta = _cliente("gerencia").patch(f"/usuarios/{objetivo}/username", json={"username": "otro.nombre"})

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": mensaje}
    assert almacen[objetivo]["username"] == objetivo


def test_admin_no_edita_username_de_otra_drogueria(almacen):
    respuesta = _cliente("admin", usuario_id="admin-yo").patch(
        "/usuarios/comercial-otra/username", json={"username": "otro.nombre"}
    )

    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Un admin solo puede modificar usuarios de su droguería"}
    assert almacen["comercial-otra"]["username"] == "comercial-otra"


@pytest.mark.parametrize("rol", ["lider_comercial", "comercial", "compras"])
def test_roles_sin_gestion_no_blanquean_ni_editan_username(almacen, auth_admin, rol):
    cliente = _cliente(rol)

    assert cliente.patch("/usuarios/compras-propio/password", json={"password": "temporal2"}).status_code == 403
    assert cliente.patch("/usuarios/compras-propio/username", json={"username": "otro.nombre"}).status_code == 403
    assert auth_admin["passwords"] == []
    assert almacen["compras-propio"] == _fila("compras-propio", "compras")


# ---------------------------------------------------------------------------
# S6: el resto queda igual
# ---------------------------------------------------------------------------

def test_editar_perfil_propio_sigue_funcionando(almacen):
    respuesta = _cliente("comercial", usuario_id="comercial-propio").patch(
        "/usuarios/me", json={"nombre": "Juan"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Juan"
    assert almacen["comercial-propio"]["apellido"] is None

