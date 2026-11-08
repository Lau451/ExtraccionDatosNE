"""Router de import legado de PCP (design.md D8, spec `pcp-legacy-import`,
tasks.md Fase 8).

Gateado por la capacidad `pcp.escribir` (services/shared/permisos.py).
`/pcp/imports/presupuestos-legacy` es la excepción: solo `admin`
(`presupuestos.importar_legacy`, odd/tasks/roles-permisos-matriz.md S6).
Mantiene su path, roles, request y response, pero el import lo hace `comercial`
a través de `services.presupuestacion.presupuestos.api`
(odd/tasks/procesos-comerciales-dueno.md S1).
"""

from fastapi import APIRouter, Depends

from services.pcp.imports.models import ImportPcpLegacyRequest, ImportPcpLegacyResultado
from services.pcp.imports.service import importar_pcp_legacy_para_endpoint
from services.presupuestacion.presupuestos.api import (
    ImportPresupuestoLegacyRequest,
    ImportPresupuestoLegacyResultado,
    importar_presupuesto_legacy_para_endpoint,
)
from services.shared.auth import UsuarioPerfil, require_capacidad

router = APIRouter()


@router.post("/pcp/imports/legacy", response_model=list[ImportPcpLegacyResultado])
def importar_pcp_legacy_endpoint(
    body: ImportPcpLegacyRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("pcp.escribir")),
) -> list[ImportPcpLegacyResultado]:
    return importar_pcp_legacy_para_endpoint(
        drogueria_id=usuario.drogueria_id, filas=body.filas, usuario_id=usuario.id
    )


@router.post(
    "/pcp/imports/presupuestos-legacy", response_model=list[ImportPresupuestoLegacyResultado]
)
def importar_presupuesto_legacy_endpoint(
    body: ImportPresupuestoLegacyRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("presupuestos.importar_legacy")),
) -> list[ImportPresupuestoLegacyResultado]:
    """Sibling de `/pcp/imports/legacy`: import de presupuestos, mandatorio
    ANTES del import de PCP (agreed design, odd/tasks/
    presupuestos-legacy-import.md T1/T2 -- T2 busca por
    `presupuesto_legacy_map`, nunca crea el presupuesto)."""
    return importar_presupuesto_legacy_para_endpoint(
        drogueria_id=usuario.drogueria_id, filas=body.filas, usuario_id=usuario.id
    )
