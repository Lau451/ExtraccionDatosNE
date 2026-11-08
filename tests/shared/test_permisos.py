"""tests/shared/test_permisos.py -- matriz única rol → capacidad
(odd/tasks/roles-capacidades.md S1-S3). La tabla esperada es la traducción 1:1
de las tuplas de roles que cada módulo tenía escritas antes de la etapa 5: si
cambia un permiso, cambia acá a propósito."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services.shared.auth import UsuarioPerfil, get_current_user, require_capacidad
from services.shared.exceptions import register_exception_handlers
from services.shared.permisos import (
    MATRIZ,
    CapacidadDesconocidaError,
    capacidades_de,
    tiene_capacidad,
)

TODOS = {"superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"}
COMERCIAL = {"admin", "gerencia", "lider_comercial", "comercial"}
TERCEROS_ESCRITURA = {"admin", "gerencia", "lider_comercial"}

ESPERADA: dict[str, set[str]] = {
    # services/pcp/roles.py
    "pcp.leer": {"superadmin", "admin", "gerencia", "compras"},
    "pcp.escribir": {"admin", "gerencia", "compras"},
    # services/terceros/*/router.py
    "terceros.leer": TODOS,
    "terceros.escribir": TERCEROS_ESCRITURA,
    "terceros.contactos.leer": TODOS,
    "terceros.contactos.escribir": TERCEROS_ESCRITURA,
    "terceros.direcciones.leer": TODOS,
    "terceros.direcciones.escribir": TERCEROS_ESCRITURA,
    "terceros.catalogos.leer": TODOS,
    "terceros.catalogos.escribir": TERCEROS_ESCRITURA,
    # services/productos/router.py
    "productos.leer": TODOS,
    "productos.escribir": {"admin", "gerencia", "compras"},
    "productos.categorias.escribir": {"admin", "gerencia"},
    "productos.costos.leer": {"superadmin", "admin", "gerencia", "lider_comercial", "compras"},
    # services/integracion_progress/router.py
    "integracion_progress.leer": TODOS,
    # services/presupuestacion/presupuestos/importacion_legacy.py
    "presupuestos.importar_legacy": {"admin"},
    # services/extraccion/auth.py
    "extraccion.extraer": COMERCIAL,
    # services/presupuestacion/*
    "auditoria.leer": TODOS,
    "automatizaciones.gestionar": {"admin", "gerencia"},
    "clientes.leer": TODOS,
    "clientes.escribir": COMERCIAL,
    "comparativas.leer": TODOS,
    "comparativas.asignar": COMERCIAL,
    "compras.leer": TODOS,
    "compras.oc": COMERCIAL,
    "compras.entregas": COMERCIAL,
    "compras.vs_cotizado": {"superadmin", "admin", "gerencia", "compras"},
    "compromisos.leer": TODOS,
    "droguerias.gestionar": {"superadmin"},
    "eventos.leer": TODOS,
    "eventos.escribir": {"admin", "gerencia", "lider_comercial", "comercial", "compras"},
    "eventos.eliminar": {"admin", "gerencia"},
    "extraccion.listar": COMERCIAL,
    "extraccion.validar": COMERCIAL,
    "imports.importar": {"admin", "gerencia", "compras"},
    "matching.usar": {"superadmin", "admin", "gerencia", "lider_comercial", "comercial"},
    "oc_entregas.planificar": COMERCIAL,
    "oc_export.exportar": COMERCIAL,
    "oc_presupuesto.matching": COMERCIAL,
    "oc_resumen.leer": TODOS,
    "presupuestos.leer": {"superadmin", "admin", "gerencia", "lider_comercial", "comercial"},
    "presupuestos.aprobar": {"superadmin", "admin", "gerencia", "lider_comercial"},
    "presupuestos.ajustar": {"superadmin", "admin", "gerencia", "lider_comercial", "comercial"},
    "presupuestos.presentar": {"superadmin", "admin", "gerencia", "lider_comercial", "comercial"},
    "presupuestos.ver_costo": {"superadmin", "admin", "gerencia"},
    "pricing.generar_presupuesto": {"superadmin", "admin", "gerencia", "lider_comercial", "comercial"},
    "pricing.precios_especiales": {"superadmin", "admin", "gerencia", "compras"},
    "procesos_comerciales.leer": TODOS,
    "procesos_comerciales.escribir": COMERCIAL,
    "usuarios.gestionar": {"superadmin", "admin", "gerencia"},
    # Solo pantallas del frontend: difieren de la tupla de su API (S2).
    "compromisos.ver_pantalla": {"admin", "gerencia", "lider_comercial", "comercial", "compras"},
    "oc_resumen.acciones": COMERCIAL,
}


def test_matriz_es_la_traduccion_uno_a_uno_de_las_tuplas():
    assert {cap: set(roles) for cap, roles in MATRIZ.items()} == ESPERADA


def test_matriz_no_se_puede_modificar_en_runtime():
    with pytest.raises(TypeError):
        MATRIZ["pcp.leer"] = frozenset({"comercial"})  # type: ignore[index]


@pytest.mark.parametrize(
    ("rol", "capacidad", "esperado"),
    [
        ("compras", "pcp.escribir", True),
        ("superadmin", "pcp.escribir", False),
        ("comercial", "presupuestos.importar_legacy", False),
        ("admin", "presupuestos.importar_legacy", True),
        ("sistema", "pcp.leer", False),
    ],
)
def test_tiene_capacidad(rol, capacidad, esperado):
    assert tiene_capacidad(rol, capacidad) is esperado


def test_capacidad_desconocida_es_un_error_y_no_un_deny():
    with pytest.raises(CapacidadDesconocidaError):
        tiene_capacidad("admin", "pcp.borrar_todo")


def test_capacidades_de_un_rol_ordenadas():
    assert capacidades_de("superadmin") == sorted(
        cap for cap, roles in ESPERADA.items() if "superadmin" in roles
    )
    assert capacidades_de("sistema") == []


def test_require_capacidad_desconocida_falla_al_declarar_el_endpoint():
    with pytest.raises(CapacidadDesconocidaError):
        require_capacidad("pcp.borrar_todo")


def _app(rol: str) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/pcp")
    def _pcp(usuario: UsuarioPerfil = Depends(require_capacidad("pcp.escribir"))) -> dict:
        return {"rol": usuario.rol}

    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(id="u", drogueria_id="d", rol=rol)
    return TestClient(app)


def test_require_capacidad_deja_pasar_al_rol_con_la_capacidad():
    respuesta = _app("compras").get("/pcp")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"rol": "compras"}


def test_require_capacidad_responde_403_como_require_roles():
    respuesta = _app("comercial").get("/pcp")
    assert respuesta.status_code == 403
    assert "No tenés permisos para esta acción" in respuesta.text
