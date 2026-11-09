"""Fachada de `services/presupuestacion/procesos_comerciales/` para otros
módulos (X-ARQ-002, odd/tasks/pcp-fachadas.md S3).

`comercial` es el dueño de `items_proceso`; `services/pcp` busca los ítems de
un proceso solo por acá (`tests/arquitectura/test_duenos_tablas.py` falla si
`services/pcp` nombra la tabla). Este archivo no define lógica propia.
"""

from services.presupuestacion.procesos_comerciales.repository import (
    buscar_item_proceso,
    buscar_item_proceso_por_renglon,
)

__all__ = [
    "buscar_item_proceso",
    "buscar_item_proceso_por_renglon",
]
