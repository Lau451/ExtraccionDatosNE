"""Modelos del import legado de presupuestos (Progress; engram #647, agreed
design 2026-09-24, odd/tasks/presupuestos-legacy-import.md T1). Movidos desde
`services/pcp/imports/models.py` (odd/tasks/procesos-comerciales-dueno.md S1):
el dueño de las tablas comerciales es `comercial`.

El export de presupuestos trae TODAS las líneas cotizadas del proceso
comercial -- a diferencia del export de PCP (`FilaImportPcpLegacy` en
`services/pcp/imports/models.py`), que trae solo el subconjunto en negociación
con el mismo número de renglón. Import order es mandatorio: presupuesto PRIMERO
(crea proceso_comercial + presupuesto + items_proceso + presupuesto_items), PCP
DESPUÉS (busca las líneas ya existentes vía `presupuesto_legacy_map`, nunca las
crea -- T2).
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

# "1" = cotización directa, "2" = licitación. Ausente -> default `licitacion`
# (decisión confirmada por el usuario, no `cotizacion`). Copia propia del mismo
# Literal de `services/pcp/imports/models.py` (D1: presupuestacion no importa pcp).
ProcesoComercialLegacy = Literal["1", "2"]


class FilaImportPresupuestoLegacy(BaseModel):
    """Una fila del export legado de presupuestos. Los campos de cabecera
    (todo salvo `renglon`/`codigo_producto`/`descripcion_producto`/
    `cantidad_producto`/`precio_producto`) se repiten en cada fila que
    comparte `numero_presupuesto` -- el servicio usa la primera fila de cada
    grupo como cabecera, mismo criterio que el import de PCP."""

    codigo_cliente: str
    razon_social_cliente: str
    numero_presupuesto: str
    proceso_comercial: ProcesoComercialLegacy | None = None
    fecha_generacion: str | None = None
    renglon: int
    codigo_producto: str | None = None
    descripcion_producto: str
    cantidad_producto: Decimal
    precio_producto: Decimal | None = None
    importe_total: Decimal | None = None


class ImportPresupuestoLegacyRequest(BaseModel):
    filas: list[FilaImportPresupuestoLegacy]


class ImportPresupuestoLegacyResultado(BaseModel):
    codigo_legacy: str
    presupuesto_id: str
    accion: Literal["creado", "existente"]
    renglones_procesados: int
    renglones_sin_producto: int
