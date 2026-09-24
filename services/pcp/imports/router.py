"""Router de import legado de PCP (design.md D8, spec `pcp-legacy-import`,
tasks.md Fase 8).

Gateado por `ROLES_ESCRITURA_PCP` (`services/pcp/roles.py`, D11) -- mismo
rol-set que `services/presupuestacion/imports/router.py::_ROLES_IMPORT`
(`admin`,`gerencia`,`compras`), pero reusando la constante compartida del
módulo en vez de declarar una copia local, mismo criterio que el resto de
`services/pcp/**`.
"""

from fastapi import APIRouter, Depends

from services.pcp.imports.models import (
    ImportPcpLegacyRequest,
    ImportPcpLegacyResultado,
    ImportPresupuestoLegacyRequest,
    ImportPresupuestoLegacyResultado,
)
from services.pcp.imports.service import (
    importar_pcp_legacy_para_endpoint,
    importar_presupuesto_legacy_para_endpoint,
)
from services.pcp.roles import ROLES_ESCRITURA_PCP
from services.shared.auth import UsuarioPerfil, require_roles

router = APIRouter()


@router.post("/pcp/imports/legacy", response_model=list[ImportPcpLegacyResultado])
def importar_pcp_legacy_endpoint(
    body: ImportPcpLegacyRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> list[ImportPcpLegacyResultado]:
    return importar_pcp_legacy_para_endpoint(
        drogueria_id=usuario.drogueria_id, filas=body.filas, usuario_id=usuario.id
    )


@router.post(
    "/pcp/imports/presupuestos-legacy", response_model=list[ImportPresupuestoLegacyResultado]
)
def importar_presupuesto_legacy_endpoint(
    body: ImportPresupuestoLegacyRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> list[ImportPresupuestoLegacyResultado]:
    """Sibling de `/pcp/imports/legacy`: import de presupuestos, mandatorio
    ANTES del import de PCP (agreed design, odd/tasks/
    presupuestos-legacy-import.md T1/T2 -- T2 busca por
    `presupuesto_legacy_map`, nunca crea el presupuesto)."""
    return importar_presupuesto_legacy_para_endpoint(
        drogueria_id=usuario.drogueria_id, filas=body.filas, usuario_id=usuario.id
    )
