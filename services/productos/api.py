"""Fachada de `services/productos/` para otros módulos (X-ARQ-004).

`productos` es el único dueño del versionado de `costos_productos`: los demás
módulos (hoy la importación de Progress en `services/presupuestacion/imports`)
versionan costos solo a través de esta fachada, nunca escribiendo la tabla.
`tests/arquitectura/test_duenos_tablas.py` falla si alguien fuera de
`services/productos/` la escribe. Este archivo no define lógica propia.
"""

from services.productos.models import CostoAVersionar
from services.productos.service import versionar_costos

__all__ = [
    "CostoAVersionar",
    "versionar_costos",
]
