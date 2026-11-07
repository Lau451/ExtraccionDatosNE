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
