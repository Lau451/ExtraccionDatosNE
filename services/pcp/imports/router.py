"""Router de import legado de PCP (design.md D8, spec `pcp-legacy-import`,
tasks.md Fase 8).

Gateado por `ROLES_ESCRITURA_PCP` (`services/pcp/roles.py`, D11) -- mismo
rol-set que `services/presupuestacion/imports/router.py::_ROLES_IMPORT`
(`admin`,`gerencia`,`compras`), pero reusando la constante compartida del
módulo en vez de declarar una copia local, mismo criterio que el resto de
`services/pcp/**`.
"""

from fastapi import APIRouter, Depends

from services.pcp.imports.models import ImportPcpLegacyRequest, ImportPcpLegacyResultado
from services.pcp.imports.service import importar_pcp_legacy_para_endpoint
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
