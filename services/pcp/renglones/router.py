from fastapi import APIRouter, Depends
from supabase import Client

from services.pcp.renglones.models import PcpRenglonCreate, PcpRenglonOut, SeleccionProveedores
from services.pcp.renglones.service import (
    crear_renglon_para_endpoint,
    listar_renglones,
    obtener_detalle_renglon,
    seleccionar_proveedores_para_endpoint,
)
from services.pcp.roles import ROLES_ESCRITURA_PCP, ROLES_LECTURA_PCP
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client

router = APIRouter()


@router.post("/pcp/{pcp_id}/renglones", response_model=PcpRenglonOut)
def crear_renglon_endpoint(
    pcp_id: str,
    body: PcpRenglonCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> PcpRenglonOut:
    return crear_renglon_para_endpoint(
        drogueria_id=usuario.drogueria_id, pcp_id=pcp_id, body=body, usuario_id=usuario.id
    )


@router.get("/pcp/{pcp_id}/renglones", response_model=list[PcpRenglonOut])
def listar_renglones_endpoint(
    pcp_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> list[PcpRenglonOut]:
    return listar_renglones(user_client, pcp_id=pcp_id, drogueria_id=usuario.drogueria_id)


@router.get("/pcp/{pcp_id}/renglones/{renglon_id}")
def obtener_detalle_renglon_endpoint(
    pcp_id: str,
    renglon_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> dict:
    return obtener_detalle_renglon(user_client, renglon_id=renglon_id, drogueria_id=usuario.drogueria_id)


@router.post("/pcp/{pcp_id}/renglones/{renglon_id}/proveedores", response_model=list[dict])
def seleccionar_proveedores_endpoint(
    pcp_id: str,
    renglon_id: str,
    body: SeleccionProveedores,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> list[dict]:
    return seleccionar_proveedores_para_endpoint(
        renglon_id=renglon_id, drogueria_id=usuario.drogueria_id, proveedor_ids=body.proveedor_ids
    )
