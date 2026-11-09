"""Fachada de `services/presupuestacion/pricing/` para otros módulos
(X-ARQ-002, odd/tasks/pcp-fachadas.md S1).

Hoy la consume `services/pcp/negociacion/service.py`, que regenera el
presupuesto cuando se cierra un PCP con `PCP_REPRICING_AUTOMATICO` prendido.
Este archivo no define lógica propia.
"""

from services.presupuestacion.pricing.service import generar_presupuesto_para_endpoint

__all__ = [
    "generar_presupuesto_para_endpoint",
]
