"""Routers de presupuestación agrupados por módulo objetivo (X-ARQ-006,
odd/tasks/routers-por-modulo.md S1).

`main.py` monta un router por entrada de `MODULOS`, en este orden. Cada módulo
agrupa los routers que `docs/arquitectura/mapa-modulos.md` le asigna, sin mover
carpetas (P10): las rutas HTTP y sus tags de OpenAPI quedan iguales. Vive acá, en
la raíz de composición, porque `services/terceros` y `services/productos` no
pueden importar `presupuestacion` (`tests/arquitectura/test_capas.py`).
Lo protege `tests/arquitectura/test_routers_por_modulo.py`.
"""

from dataclasses import dataclass

from fastapi import APIRouter

from services.integracion_progress.router import router as integracion_progress_router
from services.pcp.router import router as pcp_router
from services.presupuestacion.auditoria.router import router as auditoria_router
from services.presupuestacion.auth.router import router as auth_router
from services.presupuestacion.automatizaciones.router import router as automatizaciones_router
from services.presupuestacion.clientes.router import router as clientes_router
from services.presupuestacion.comparativas.router import router as comparativas_router
from services.presupuestacion.compras.router import router as compras_router
from services.presupuestacion.compromisos.router import router as compromisos_router
from services.presupuestacion.droguerias.router import router as droguerias_router
from services.presupuestacion.eventos.router import router as eventos_router
from services.presupuestacion.extraccion.router import router as extraccion_router
from services.presupuestacion.imports.router import router as imports_router
from services.presupuestacion.matching.router import router as matching_router
from services.presupuestacion.notificaciones.router import router as notificaciones_router
from services.presupuestacion.oc_entregas.router import router as oc_entregas_router
from services.presupuestacion.oc_export.router import router as oc_export_router
from services.presupuestacion.oc_presupuesto.router import router as oc_presupuesto_router
from services.presupuestacion.oc_resumen.router import router as oc_resumen_router
from services.presupuestacion.planes.router import router as planes_router
from services.presupuestacion.presupuestos.router import router as presupuestos_router
from services.presupuestacion.pricing.router import router as pricing_router
from services.presupuestacion.procesos_comerciales.router import router as procesos_comerciales_router
from services.presupuestacion.usuarios.router import router as usuarios_router
from services.productos.router import router as productos_router
from services.terceros.router import router as terceros_router


@dataclass(frozen=True)
class Modulo:
    nombre: str
    router: APIRouter


def _modulo(nombre: str, routers: list[tuple[APIRouter, str]]) -> Modulo:
    """Un `APIRouter` que incluye cada router con su tag de siempre."""
    agrupado = APIRouter()
    for router, tag in routers:
        agrupado.include_router(router, tags=[tag])
    return Modulo(nombre, agrupado)


MODULOS: list[Modulo] = [
    _modulo(
        "plataforma",
        [
            (auth_router, "auth"),
            (usuarios_router, "usuarios"),
            (droguerias_router, "droguerias"),
            (planes_router, "planes"),
            (eventos_router, "eventos"),
            (notificaciones_router, "notificaciones"),
            (auditoria_router, "auditoria"),
        ],
    ),
    _modulo("productos", [(productos_router, "productos"), (imports_router, "imports")]),
    _modulo("terceros", [(terceros_router, "terceros"), (clientes_router, "clientes")]),
    _modulo(
        "comercial",
        [
            (pricing_router, "pricing"),
            (matching_router, "matching"),
            (presupuestos_router, "presupuestos"),
            (extraccion_router, "extraccion"),
            (comparativas_router, "comparativas"),
            (procesos_comerciales_router, "procesos_comerciales"),
        ],
    ),
    _modulo("compras", [(compras_router, "compras"), (pcp_router, "pcp")]),
    _modulo(
        "ordenes_compra",
        [
            (oc_presupuesto_router, "oc_presupuesto"),
            (oc_entregas_router, "oc_entregas"),
            (oc_resumen_router, "oc_resumen"),
            (compromisos_router, "compromisos"),
        ],
    ),
    _modulo(
        "integracion_progress",
        [(oc_export_router, "oc_export"), (integracion_progress_router, "integracion_progress")],
    ),
    _modulo("automatizaciones", [(automatizaciones_router, "automatizaciones")]),
]
