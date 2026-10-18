"""Matriz de roles del backend (odd/tasks/roles-permisos-matriz.md, T1/T2:
S1, S2, S3, S4, S5, S6, S8).

Tests unitarios sobre las apps reales (`services.extraccion.main:app` y
`services.presupuestacion.main:app`) con `get_current_user` sobreescrito, sin
Supabase. Para distinguir "el guard deja pasar" de "el guard rechaza" sin tocar
la base en endpoints de escritura se manda un body inválido: FastAPI resuelve
las dependencias (incluido `require_roles`) antes de validar el body, así que un
rol rechazado da 403 y un rol permitido llega a la validación y da 422. Los GET
permitidos se prueban parcheando la función de servicio del router.
"""
import io
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import services.extraccion.supabase_client as sc_module
from services.extraccion.main import app as app_extraccion
from services.presupuestacion.main import app as app_presupuestacion
from services.shared.auth import UsuarioPerfil, get_current_user
from services.shared.database import get_user_client

TODOS = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


def _perfil(rol: str) -> UsuarioPerfil:
    # drogueria_id seteado siempre: el 403 tiene que venir del rol, no de la
    # falta de droguería (services/extraccion/auth.py::get_drogueria_id_actual).
    return UsuarioPerfil(id="u-1", drogueria_id="d-1", rol=rol)


@pytest.fixture(autouse=True)
def _limpiar_overrides():
    sc_module.reset_client_for_testing()
    yield
    sc_module.reset_client_for_testing()
    for app in (app_extraccion, app_presupuestacion):
        app.dependency_overrides.clear()


def _cliente(app, rol: str) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _perfil(rol)
    app.dependency_overrides[get_user_client] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# S1 -- services/extraccion: solo admin, gerencia, lider_comercial, comercial
# ---------------------------------------------------------------------------

ROLES_S1 = ("admin", "gerencia", "lider_comercial", "comercial")
DENEGADOS_S1 = ("superadmin", "compras")


def _llamar_extraccion(client: TestClient, endpoint: str):
    if endpoint == "procesar":
        return client.post(
            "/procesar",
            data={"tipo": ""},
            files={"archivo": ("doc.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
            headers={"Accept": "application/json"},
        )
    if endpoint == "listar_documentos":
        return client.get("/api/documentos")
    if endpoint == "detalle_documento":
        return client.get(f"/api/documentos/{uuid.uuid4()}")
    if endpoint == "patch_extraction_result":
        return client.patch(
            f"/api/extraction-results/{uuid.uuid4()}", json={"document_type": "comparativa"}
        )
    if endpoint == "listar_clientes":
        return client.get("/api/clientes")
    raise AssertionError(endpoint)


ENDPOINTS_S1 = (
    "procesar",
    "listar_documentos",
    "detalle_documento",
    "patch_extraction_result",
    "listar_clientes",
)


@pytest.mark.parametrize("rol", DENEGADOS_S1)
@pytest.mark.parametrize("endpoint", ENDPOINTS_S1)
def test_s1_extraccion_rechaza_superadmin_y_compras_con_403(endpoint, rol, mocker):
    # Todo acceso a Supabase/robot parcheado: el rechazo no puede tocar nada.
    mocks = [
        mocker.patch(f"{modulo}.get_client")
        for modulo in (
            "services.extraccion.main",
            "services.extraccion.routers.clientes",
            "services.extraccion.routers.extraction_results",
        )
    ] + [
        mocker.patch(f"services.extraccion.main.{nombre}")
        for nombre in (
            "buscar_duplicado_con_lock",
            "crear_sesion",
            "crear_extraction_processing",
            "procesar_archivo",
        )
    ]

    respuesta = _llamar_extraccion(_cliente(app_extraccion, rol), endpoint)

    assert respuesta.status_code == 403
    for mock in mocks:
        mock.assert_not_called()


@pytest.mark.parametrize("rol", ROLES_S1)
def test_s1_extraccion_roles_permitidos_siguen_listando_documentos(rol, mocker):
    mock_qb = MagicMock()
    for m in ("select", "eq", "order"):
        getattr(mock_qb, m).return_value = mock_qb
    mock_qb.execute.return_value = MagicMock(data=[])
    mock_client = MagicMock()
    mock_client.table.return_value = mock_qb
    mocker.patch("services.extraccion.main.get_client", return_value=mock_client)

    respuesta = _cliente(app_extraccion, rol).get("/api/documentos")

    assert respuesta.status_code == 200
    mock_qb.eq.assert_any_call("drogueria_id", "d-1")


def test_s1_extraccion_sin_drogueria_sigue_dando_403():
    app_extraccion.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="u-1", drogueria_id=None, rol="comercial"
    )

    respuesta = TestClient(app_extraccion, raise_server_exceptions=False).get("/api/documentos")

    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# S2 -- GET /extracciones: solo admin, gerencia, lider_comercial, comercial
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ("superadmin", "compras"))
def test_s2_listado_extracciones_rechaza_superadmin_y_compras(rol, mocker):
    mock_listar = mocker.patch(
        "services.presupuestacion.extraccion.router.listar_extracciones", return_value=[]
    )

    respuesta = _cliente(app_presupuestacion, rol).get("/extracciones")

    assert respuesta.status_code == 403
    mock_listar.assert_not_called()


@pytest.mark.parametrize("rol", ("admin", "gerencia", "lider_comercial", "comercial"))
def test_s2_listado_extracciones_roles_permitidos_siguen_con_200(rol, mocker):
    mocker.patch("services.presupuestacion.extraccion.router.listar_extracciones", return_value=[])

    respuesta = _cliente(app_presupuestacion, rol).get("/extracciones")

    assert respuesta.status_code == 200
    assert respuesta.json() == []


# ---------------------------------------------------------------------------
# S8 -- POST /ordenes-compra/{id}/entregas: compras pierde el acceso
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ("compras", "superadmin"))
def test_s8_planificar_entregas_rechaza_compras_y_superadmin(rol):
    respuesta = _cliente(app_presupuestacion, rol).post(
        "/ordenes-compra/oc-1/entregas", json={"items": "invalido"}
    )

    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ("admin", "gerencia", "lider_comercial", "comercial"))
def test_s8_planificar_entregas_roles_permitidos_pasan_el_guard(rol):
    respuesta = _cliente(app_presupuestacion, rol).post(
        "/ordenes-compra/oc-1/entregas", json={"items": "invalido"}
    )

    assert respuesta.status_code == 422


# ---------------------------------------------------------------------------
# S3 -- GET /productos/{id}/costos: agrega lider_comercial; comercial sigue sin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ("superadmin", "admin", "gerencia", "lider_comercial", "compras"))
def test_s3_ver_costos_roles_permitidos_200(rol, mocker):
    mocker.patch("services.productos.router.listar_costos_para_endpoint", return_value=[])

    respuesta = _cliente(app_presupuestacion, rol).get("/productos/p-1/costos")

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_s3_ver_costos_comercial_sigue_rechazado(mocker):
    mock_listar = mocker.patch(
        "services.productos.router.listar_costos_para_endpoint", return_value=[]
    )

    respuesta = _cliente(app_presupuestacion, "comercial").get("/productos/p-1/costos")

    assert respuesta.status_code == 403
    mock_listar.assert_not_called()


# ---------------------------------------------------------------------------
# S4 -- terceros, direcciones y contactos: escritura solo admin, gerencia,
# lider_comercial; lectura sin cambios para los 6 roles
# ---------------------------------------------------------------------------

ESCRITURAS_S4 = (
    ("post", "/terceros"),
    ("patch", "/terceros/t-1"),
    ("post", "/terceros/t-1/clientes"),
    ("patch", "/terceros/t-1/clientes"),
    ("post", "/terceros/t-1/proveedores"),
    ("patch", "/terceros/t-1/proveedores"),
    ("post", "/terceros/t-1/direcciones"),
    ("patch", "/terceros/t-1/direcciones/d-1"),
    ("post", "/terceros/t-1/direcciones/d-1/usos"),
    ("post", "/terceros/t-1/contactos"),
    ("patch", "/terceros/t-1/contactos/c-1"),
)
BORRADOS_S4 = (
    "/terceros/t-1/direcciones/d-1",
    "/terceros/t-1/direcciones/d-1/usos/entrega",
)


@pytest.mark.parametrize("rol", ("comercial", "compras", "superadmin"))
@pytest.mark.parametrize("metodo,ruta", ESCRITURAS_S4)
def test_s4_escritura_terceros_rechaza_roles_sin_permiso(metodo, ruta, rol):
    respuesta = getattr(_cliente(app_presupuestacion, rol), metodo)(ruta, json=[])

    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ("comercial", "compras"))
@pytest.mark.parametrize("ruta", BORRADOS_S4)
def test_s4_borrados_de_direcciones_rechazan_comercial_y_compras(ruta, rol, mocker):
    mock_eliminar_dir = mocker.patch(
        "services.terceros.direcciones.router.eliminar_direccion_para_endpoint"
    )
    mock_eliminar_uso = mocker.patch(
        "services.terceros.direcciones.router.eliminar_uso_para_endpoint"
    )

    respuesta = _cliente(app_presupuestacion, rol).delete(ruta)

    assert respuesta.status_code == 403
    mock_eliminar_dir.assert_not_called()
    mock_eliminar_uso.assert_not_called()


@pytest.mark.parametrize("rol", ("admin", "gerencia", "lider_comercial"))
@pytest.mark.parametrize("metodo,ruta", ESCRITURAS_S4)
def test_s4_escritura_terceros_roles_permitidos_pasan_el_guard(metodo, ruta, rol):
    respuesta = getattr(_cliente(app_presupuestacion, rol), metodo)(ruta, json=[])

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", TODOS)
def test_s4_lectura_de_contactos_sigue_abierta_a_los_6_roles(rol, mocker):
    mocker.patch("services.terceros.contactos.router.listar_contactos", return_value=[])

    respuesta = _cliente(app_presupuestacion, rol).get("/terceros/t-1/contactos")

    assert respuesta.status_code == 200


# ---------------------------------------------------------------------------
# S5 -- catálogos de apoyo: escritura admin, gerencia, lider_comercial
# ---------------------------------------------------------------------------

ESCRITURAS_S5 = (
    ("post", "/sectores-contacto"),
    ("patch", "/sectores-contacto/s-1"),
    ("post", "/condiciones-pago"),
    ("patch", "/condiciones-pago/c-1"),
    ("post", "/formas-pago"),
    ("patch", "/formas-pago/f-1"),
)


@pytest.mark.parametrize("rol", ("admin", "gerencia", "lider_comercial"))
@pytest.mark.parametrize("metodo,ruta", ESCRITURAS_S5)
def test_s5_catalogos_roles_permitidos_pasan_el_guard(metodo, ruta, rol):
    respuesta = getattr(_cliente(app_presupuestacion, rol), metodo)(ruta, json=[])

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", ("superadmin", "comercial", "compras"))
@pytest.mark.parametrize("metodo,ruta", ESCRITURAS_S5)
def test_s5_catalogos_otros_roles_siguen_rechazados(metodo, ruta, rol):
    respuesta = getattr(_cliente(app_presupuestacion, rol), metodo)(ruta, json=[])

    assert respuesta.status_code == 403


# ---------------------------------------------------------------------------
# S6 -- importar presupuestos legacy: solo admin; importar PCP sin cambios
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ("superadmin", "gerencia", "lider_comercial", "comercial", "compras"))
def test_s6_presupuestos_legacy_rechaza_todo_rol_salvo_admin(rol):
    respuesta = _cliente(app_presupuestacion, rol).post(
        "/pcp/imports/presupuestos-legacy", json={"filas": "invalido"}
    )

    assert respuesta.status_code == 403


def test_s6_presupuestos_legacy_admin_pasa_el_guard():
    respuesta = _cliente(app_presupuestacion, "admin").post(
        "/pcp/imports/presupuestos-legacy", json={"filas": "invalido"}
    )

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", ("admin", "gerencia", "compras"))
def test_s6_importar_pcp_sigue_abierto_a_admin_gerencia_compras(rol):
    respuesta = _cliente(app_presupuestacion, rol).post(
        "/pcp/imports/legacy", json={"filas": "invalido"}
    )

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", ("superadmin", "lider_comercial", "comercial"))
def test_s6_importar_pcp_sigue_rechazando_al_resto(rol):
    respuesta = _cliente(app_presupuestacion, rol).post(
        "/pcp/imports/legacy", json={"filas": "invalido"}
    )

    assert respuesta.status_code == 403
