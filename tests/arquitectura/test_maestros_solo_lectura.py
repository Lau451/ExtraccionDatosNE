"""Progress owns product and tercero masters (docs/arquitectura/maestros-progress.md,
odd/tasks/maestros-solo-lectura.md S2-S5): the manual alta, edición, baja, costo and
stock endpoints no longer exist, and the app-owned ones still do."""

import pytest
from fastapi.routing import APIRoute

from services.presupuestacion.main import app


def _rutas() -> set[tuple[str, str]]:
    return {
        (metodo, ruta.path)
        for ruta in app.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }


ELIMINADAS_PRODUCTOS = [
    ("POST", "/productos"),
    ("PATCH", "/productos/{producto_id}"),
    ("DELETE", "/productos/{producto_id}"),
    ("POST", "/productos/{producto_id}/costos"),
    ("PATCH", "/productos/{producto_id}/stock"),
]

CONSERVADAS_PRODUCTOS = [
    ("GET", "/productos"),
    ("GET", "/productos/{producto_id}"),
    ("GET", "/productos/{producto_id}/costos"),
    ("GET", "/productos/{producto_id}/stock"),
    ("POST", "/productos/{producto_id}/caracteristicas"),
    ("DELETE", "/productos/{producto_id}/caracteristicas/{caracteristica_id}"),
    ("POST", "/categorias"),
    ("POST", "/marcas"),
    ("POST", "/envases"),
    ("POST", "/caracteristicas"),
    ("POST", "/imports/productos"),
    ("POST", "/imports/costos"),
    ("POST", "/imports/stock"),
]


@pytest.mark.parametrize("metodo, ruta", ELIMINADAS_PRODUCTOS)
def test_endpoint_manual_de_producto_eliminado(metodo, ruta):
    assert (metodo, ruta) not in _rutas()


@pytest.mark.parametrize("metodo, ruta", CONSERVADAS_PRODUCTOS)
def test_endpoint_de_producto_que_sigue(metodo, ruta):
    assert (metodo, ruta) in _rutas()


ELIMINADAS_TERCEROS = [
    ("POST", "/terceros"),
    ("POST", "/terceros/{tercero_id}/clientes"),
    ("POST", "/terceros/{tercero_id}/proveedores"),
    ("POST", "/clientes"),
    ("DELETE", "/clientes/{cliente_id}"),
]

CONSERVADAS_TERCEROS = [
    ("PATCH", "/terceros/{tercero_id}"),
    ("PATCH", "/terceros/{tercero_id}/clientes"),
    ("PATCH", "/terceros/{tercero_id}/proveedores"),
    ("PATCH", "/clientes/{cliente_id}"),
    ("POST", "/clientes/{cliente_id}/contactos"),
    ("POST", "/imports/clientes"),
    ("POST", "/imports/proveedores"),
]


@pytest.mark.parametrize("metodo, ruta", ELIMINADAS_TERCEROS)
def test_endpoint_manual_de_tercero_eliminado(metodo, ruta):
    assert (metodo, ruta) not in _rutas()


@pytest.mark.parametrize("metodo, ruta", CONSERVADAS_TERCEROS)
def test_endpoint_de_tercero_que_sigue(metodo, ruta):
    assert (metodo, ruta) in _rutas()


# PATCH: (ruta, función de servicio del router, campos de Progress, campos de la app)
_PATCHES = [
    (
        "/terceros/t-1",
        "services.terceros.identidad.router.actualizar_tercero_para_endpoint",
        {"codigo_interno": "X", "razon_social": "X", "cuit": "20111111112", "activo": False},
        {"nombre_fantasia": "F", "email": "a@b.com", "telefono": "1", "sitio_web": "w", "notas": "n"},
    ),
    (
        "/terceros/t-1/clientes",
        "services.terceros.identidad.router.actualizar_rol_cliente_para_endpoint",
        {"tipo": "otro", "activo": False},
        {"condicion_pago_id": "c-1", "forma_pago_id": "f-1"},
    ),
    (
        "/terceros/t-1/proveedores",
        "services.terceros.identidad.router.actualizar_rol_proveedor_para_endpoint",
        {"tipo": "otro", "es_competidor": True, "es_proveedor_compra": True, "activo": False},
        {"condicion_pago_id": "c-1", "forma_pago_id": "f-1"},
    ),
    (
        "/clientes/c-1",
        "services.presupuestacion.clientes.router.actualizar_cliente_para_endpoint",
        {"nombre": "X", "cuit": "20111111112", "tipo": "otro", "activo": False},
        {"email": "a@b.com", "telefono": "1", "condicion_pago_id": "c-1", "forma_pago_id": "f-1"},
    ),
]


def _cliente_admin():
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from services.shared.auth import UsuarioPerfil, get_current_user
    from services.shared.database import get_user_client

    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(id="u-1", drogueria_id="d-1", rol="admin")
    app.dependency_overrides[get_user_client] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cliente_admin():
    yield _cliente_admin()
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "ruta, servicio, campo, valor",
    [(r, s, c, v) for r, s, progress, _ in _PATCHES for c, v in progress.items()],
)
def test_patch_rechaza_campo_de_progress(cliente_admin, mocker, ruta, servicio, campo, valor):
    llamado = mocker.patch(servicio)

    respuesta = cliente_admin.patch(ruta, json={campo: valor})

    assert respuesta.status_code == 422
    assert campo in respuesta.text
    llamado.assert_not_called()


@pytest.mark.parametrize("ruta, servicio, _progress, app_campos", _PATCHES)
def test_patch_acepta_campos_de_la_app(cliente_admin, mocker, ruta, servicio, _progress, app_campos):
    llamado = mocker.patch(servicio)

    cliente_admin.patch(ruta, json=app_campos)

    llamado.assert_called_once()
    assert llamado.call_args.kwargs["body"].model_dump(exclude_unset=True) == app_campos
