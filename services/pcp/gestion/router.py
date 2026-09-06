from fastapi import APIRouter, Depends
from supabase import Client

from services.pcp.gestion.models import PcpCreate, PcpOut, PcpTransicionEstado
from services.pcp.gestion.service import (
    cambiar_estado_para_endpoint,
    crear_pcp_para_endpoint,
    listar_pcp,
    obtener_pcp,
)
from services.pcp.roles import ROLES_ESCRITURA_PCP, ROLES_LECTURA_PCP
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client

router = APIRouter()


def _es_superadmin(usuario: UsuarioPerfil) -> bool:
    return usuario.rol == "superadmin"


@router.post("/pcp", response_model=PcpOut)
def crear_pcp_endpoint(
    body: PcpCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> PcpOut:
    return crear_pcp_para_endpoint(drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id)


@router.get("/pcp", response_model=list[PcpOut])
def listar_pcp_endpoint(
    estado: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> list[PcpOut]:
    return listar_pcp(
        user_client,
        drogueria_id=usuario.drogueria_id,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@router.get("/pcp/{pcp_id}", response_model=PcpOut)
def obtener_pcp_endpoint(
    pcp_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> PcpOut:
    return obtener_pcp(
        user_client,
        pcp_id=pcp_id,
        drogueria_id=usuario.drogueria_id,
        es_superadmin=_es_superadmin(usuario),
    )


@router.patch("/pcp/{pcp_id}/estado", response_model=PcpOut)
def cambiar_estado_endpoint(
    pcp_id: str,
    body: PcpTransicionEstado,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> PcpOut:
    return cambiar_estado_para_endpoint(
        pcp_id=pcp_id,
        drogueria_id=usuario.drogueria_id,
        estado_nuevo=body.estado,
        usuario_id=usuario.id,
        es_superadmin=_es_superadmin(usuario),
    )
