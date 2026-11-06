"""Fachada de `services/presupuestacion/presupuestos/` para consumidores de
otros módulos (mismo criterio que `services/pcp/api.py`).

Expone el import legado de presupuestos (odd/tasks/procesos-comerciales-dueno.md
S1): `comercial` es el dueño de la materialización del presupuesto legado
(proceso, ítems, presupuesto y su mapa). Lo consumen
`POST /pcp/imports/presupuestos-legacy` (`services/pcp/imports/router.py`) y
`services/integracion_progress`, que le entrega el archivo de Progress. No
define lógica propia: reexporta modelos, funciones de servicio y el rol-set del
import.
"""

from services.presupuestacion.presupuestos.importacion_legacy import (
    ROLES_IMPORT_PRESUPUESTOS_LEGACY,
    importar_presupuesto_legacy,
    importar_presupuesto_legacy_para_endpoint,
)
from services.presupuestacion.presupuestos.importacion_legacy_models import (
    FilaImportPresupuestoLegacy,
    ImportPresupuestoLegacyRequest,
    ImportPresupuestoLegacyResultado,
)

__all__ = [
    # import legado de presupuestos -- modelos
    "FilaImportPresupuestoLegacy",
    "ImportPresupuestoLegacyRequest",
    "ImportPresupuestoLegacyResultado",
    # import legado de presupuestos -- funciones
    "importar_presupuesto_legacy",
    "importar_presupuesto_legacy_para_endpoint",
    # import legado de presupuestos -- roles
    "ROLES_IMPORT_PRESUPUESTOS_LEGACY",
]
