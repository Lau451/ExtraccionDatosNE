from fastapi import APIRouter, Depends
from supabase import Client

from services.pcp.negociacion.models import RegistrarResultadoNegociacion, ResultadoNegociacionOut
from services.pcp.negociacion.service import (
    obtener_resultado,
    registrar_resultado_para_endpoint,
)
from services.pcp.roles import ROLES_ESCRITURA_PCP, ROLES_LECTURA_PCP
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client

router = APIRouter()


@router.post(
    "/pcp/{pcp_id}/renglones/{renglon_id}/proveedores/{proveedor_id}/resultado",
    response_model=ResultadoNegociacionOut,
)
def registrar_resultado_endpoint(
    pcp_id: str,
    renglon_id: str,
    proveedor_id: str,
    body: RegistrarResultadoNegociacion,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> ResultadoNegociacionOut:
    return registrar_resultado_para_endpoint(
        drogueria_id=usuario.drogueria_id,
        pcp_renglon_id=renglon_id,
        proveedor_id=proveedor_id,
        body=body,
        usuario_id=usuario.id,
    )


@router.get(
    "/pcp/{pcp_id}/renglones/{renglon_id}/proveedores/{proveedor_id}/resultado",
    response_model=ResultadoNegociacionOut,
)
def obtener_resultado_endpoint(
    pcp_id: str,
    renglon_id: str,
    proveedor_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoNegociacionOut:
    return obtener_resultado(
        user_client,
        drogueria_id=usuario.drogueria_id,
        pcp_renglon_id=renglon_id,
        proveedor_id=proveedor_id,
    )
