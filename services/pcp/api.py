"""Fachada unidireccional de `services/pcp/` (design.md D1, File Changes;
mismo criterio que `services/terceros/api.py`, D5).

D1 exige que `services.presupuestacion` solo importe `services.pcp` desde
`main.py` (el montaje del router) -- ningún módulo consume este facade en
este PR, y `tests/pcp/test_dependencias.py::test_presupuestacion_solo_importa_pcp_desde_main`
lo hace cumplir. Existe igual, junto al agregador (`router.py`), porque
`design.md` lo lista explícitamente en el "File Changes" de la Fase 5 --
mismo motivo que `services/terceros/api.py`: un único punto de entrada
público para un consumidor futuro fuera de `services/presupuestacion/main.py`
(otro módulo top-level, o un test de integración cross-módulo), en vez de
que ese consumidor tenga que conocer la estructura interna de cada
submódulo de PCP. No define lógica propia: reexporta modelos y funciones de
servicio de `gestion`, `historial` y `renglones`.
"""

from services.pcp.gestion.models import PcpCreate, PcpOut, PcpTransicionEstado
from services.pcp.gestion.service import (
    cambiar_estado,
    cambiar_estado_para_endpoint,
    crear_pcp,
    crear_pcp_para_endpoint,
    listar_pcp,
    obtener_pcp,
)
from services.pcp.historial.models import EventoHistorialCreate, EventoHistorialOut, TipoEvento
from services.pcp.historial.service import agregar_evento, listar_eventos
from services.pcp.renglones.models import (
    PcpRenglonCreate,
    PcpRenglonOut,
    RenglonDetalleOut,
    SeleccionProveedores,
)
from services.pcp.renglones.service import (
    crear_renglon,
    crear_renglon_para_endpoint,
    listar_renglones,
    listar_renglones_para_endpoint,
    obtener_detalle_renglon,
    obtener_detalle_renglon_para_endpoint,
    obtener_renglon,
    seleccionar_proveedores,
    seleccionar_proveedores_para_endpoint,
)

__all__ = [
    # gestion -- modelos
    "PcpCreate",
    "PcpOut",
    "PcpTransicionEstado",
    # gestion -- funciones
    "crear_pcp",
    "crear_pcp_para_endpoint",
    "obtener_pcp",
    "listar_pcp",
    "cambiar_estado",
    "cambiar_estado_para_endpoint",
    # historial -- modelos
    "TipoEvento",
    "EventoHistorialCreate",
    "EventoHistorialOut",
    # historial -- funciones
    "agregar_evento",
    "listar_eventos",
    # renglones -- modelos
    "PcpRenglonCreate",
    "PcpRenglonOut",
    "RenglonDetalleOut",
    "SeleccionProveedores",
    # renglones -- funciones
    "crear_renglon",
    "crear_renglon_para_endpoint",
    "obtener_renglon",
    "listar_renglones",
    "listar_renglones_para_endpoint",
    "obtener_detalle_renglon",
    "obtener_detalle_renglon_para_endpoint",
    "seleccionar_proveedores",
    "seleccionar_proveedores_para_endpoint",
]
