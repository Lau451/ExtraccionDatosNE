"""Router de sugerencias de PCP (design.md D12, spec `pcp-sugerencias`).

Solo lectura: ambos endpoints usan `user_client` (RLS-scoped) directamente,
como los GET de `services/pcp/gestion/router.py` -- ninguno necesita el
wrapper `service_role` (`_para_endpoint`), que este módulo, a diferencia de
los que sí escriben, no define. Gateados por `ROLES_LECTURA_PCP` únicamente
(D11): son sugerencias de solo lectura, sin ningún rol de escritura
adicional que exigir para poder verlas -- mismo criterio explícito del
launch prompt de esta fase.
"""

from fastapi import APIRouter, Depends
from supabase import Client

from services.pcp.roles import ROLES_LECTURA_PCP
from services.pcp.sugerencias.models import SugerenciaAgrupacionOut, SugerenciaPrecioRecienteOut
from services.pcp.sugerencias.service import (
    DIAS_VENTANA_AGRUPACION_DEFAULT,
    sugerir_agrupacion_por_renglon,
    sugerir_precios_recientes_por_renglon,
)
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client

router = APIRouter()


@router.get(
    "/pcp/sugerencias/renglones/{renglon_id}/agrupacion",
    response_model=SugerenciaAgrupacionOut | None,
)
def sugerir_agrupacion_endpoint(
    renglon_id: str,
    dias: int = DIAS_VENTANA_AGRUPACION_DEFAULT,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> SugerenciaAgrupacionOut | None:
    return sugerir_agrupacion_por_renglon(
        user_client, renglon_id=renglon_id, drogueria_id=usuario.drogueria_id, dias=dias
    )


@router.get(
    "/pcp/sugerencias/renglones/{renglon_id}/precios-recientes",
    response_model=list[SugerenciaPrecioRecienteOut],
)
def sugerir_precios_recientes_endpoint(
    renglon_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> list[SugerenciaPrecioRecienteOut]:
    return sugerir_precios_recientes_por_renglon(
        user_client, renglon_id=renglon_id, drogueria_id=usuario.drogueria_id
    )
