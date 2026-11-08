"""Fachada de `services/presupuestacion/notificaciones/` para otros módulos
(X-ARQ-002, odd/tasks/pcp-fachadas.md S1).

Hoy la consume `services/pcp/negociacion/service.py`, que avisa al solicitante
cuando se cierra un PCP. Este archivo no define lógica propia.
"""

from services.presupuestacion.notificaciones.service import crear_notificacion

__all__ = [
    "crear_notificacion",
]
