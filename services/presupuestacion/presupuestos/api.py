"""Fachada de `services/presupuestacion/presupuestos/` para consumidores de
otros módulos (mismo criterio que `services/pcp/api.py`).

Expone el import legado de presupuestos (odd/tasks/procesos-comerciales-dueno.md
S1): `comercial` es el dueño de la materialización del presupuesto legado
(proceso, ítems, presupuesto y su mapa). Lo consumen
`POST /pcp/imports/presupuestos-legacy` (`services/pcp/imports/router.py`) y
`services/integracion_progress`, que le entrega el archivo de Progress.

También expone las lecturas de `presupuestos` y `presupuesto_legacy_map` que
hace `services/pcp` (X-ARQ-002, odd/tasks/pcp-fachadas.md S3): `pcp` ya no
nombra esas tablas. `buscar_presupuesto` no filtra `deleted_at`, igual que las
lecturas que `pcp` hacía directo.

No define lógica propia: reexporta modelos y funciones.
"""

from services.presupuestacion.presupuestos.importacion_legacy import (
    importar_presupuesto_legacy,
    importar_presupuesto_legacy_para_endpoint,
)
from services.presupuestacion.presupuestos.importacion_legacy_models import (
    FilaImportPresupuestoLegacy,
    ImportPresupuestoLegacyRequest,
    ImportPresupuestoLegacyResultado,
)
from services.presupuestacion.presupuestos.importacion_legacy_repository import (
    buscar_mapa_legacy_presupuesto,
    buscar_presupuesto,
)

__all__ = [
    # import legado de presupuestos -- modelos
    "FilaImportPresupuestoLegacy",
    "ImportPresupuestoLegacyRequest",
    "ImportPresupuestoLegacyResultado",
    # import legado de presupuestos -- funciones
    "importar_presupuesto_legacy",
    "importar_presupuesto_legacy_para_endpoint",
    # lecturas para otros módulos (X-ARQ-002)
    "buscar_mapa_legacy_presupuesto",
    "buscar_presupuesto",
]
