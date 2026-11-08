"""Etapa 5 (odd/tasks/roles-capacidades.md S2-S5): cada ruta de presupuestacion
tiene a lo sumo un guard de capacidad, y las rutas sin guard son exactamente las
conocidas (solo exigen sesión). Una ruta nueva sin `require_capacidad` rompe este
test a propósito."""

from fastapi.routing import APIRoute

from services.presupuestacion.main import app

_SIN_GUARD = {
    ("GET", "/droguerias"),
    ("GET", "/droguerias/{drogueria_id}"),
    ("GET", "/notificacion-preferencias"),
    ("PUT", "/notificacion-preferencias"),
    ("GET", "/notificaciones/no-leidas"),
    ("PATCH", "/notificaciones/{notificacion_id}/archivar"),
    ("PATCH", "/notificaciones/{notificacion_id}/leer"),
    ("GET", "/planes"),
    ("GET", "/usuarios"),
    ("GET", "/usuarios/{usuario_id}"),
    ("PATCH", "/usuarios/me"),
    ("POST", "/auth/cambiar-password"),
    ("POST", "/auth/login"),
    ("GET", "/auth/capacidades"),
}


def _guards(dependant):
    for sub in dependant.dependencies:
        if "require_roles.<locals>" in getattr(sub.call, "__qualname__", ""):
            yield sub.call
        yield from _guards(sub)


def test_cada_ruta_tiene_a_lo_sumo_un_guard_y_las_abiertas_son_las_conocidas():
    abiertas = set()
    for ruta in app.routes:
        if isinstance(ruta, APIRoute):
            cantidad = len(list(_guards(ruta.dependant)))
            assert cantidad <= 1, ruta.path
            if cantidad == 0:
                abiertas |= {(metodo, ruta.path) for metodo in ruta.methods}
    assert abiertas == _SIN_GUARD
