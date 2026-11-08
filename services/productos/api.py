"""Fachada de `services/productos/` para otros módulos (X-ARQ-004, X-ARQ-002).

`productos` es el único dueño del versionado de `costos_productos`: los demás
módulos (hoy la importación de Progress en `services/presupuestacion/imports`)
versionan costos solo a través de esta fachada, nunca escribiendo la tabla.
`tests/arquitectura/test_duenos_tablas.py` falla si alguien fuera de
`services/productos/` la escribe. `services/pcp/**` lee productos por
`obtener_producto` (odd/tasks/pcp-fachadas.md S2). Este archivo no define
lógica propia.
"""

from services.productos.models import CostoAVersionar, ProductoOut
from services.productos.service import obtener_producto, versionar_costos

__all__ = [
    "CostoAVersionar",
    "ProductoOut",
    "obtener_producto",
    "versionar_costos",
]
