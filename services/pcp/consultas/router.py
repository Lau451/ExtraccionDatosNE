"""Router de `pcp-consultas-agrupadas` (design.md D9, spec
`pcp-consultas-agrupadas`, tasks.md 9.7).

Sin endpoint de envío en este PR -- ver docstring de `service.py`, el envío
real es PR11 (`services/pcp/mensajeria/`).
"""

from fastapi import APIRouter, Depends, Response
from supabase import Client

from services.pcp.consultas.models import AgruparConsultaCreate, ConsultaOut
from services.pcp.consultas.service import (
    agrupar_renglones_para_endpoint,
    enviar_consulta_para_endpoint,
    generar_pdf_consulta_para_endpoint,
    obtener_consulta,
)
from services.pcp.roles import ROLES_ESCRITURA_PCP, ROLES_LECTURA_PCP
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_user_client

router = APIRouter()


@router.post("/pcp/consultas", response_model=list[ConsultaOut])
def agrupar_renglones_endpoint(
    body: AgruparConsultaCreate,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> list[ConsultaOut]:
    return agrupar_renglones_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.get("/pcp/consultas/{consulta_id}", response_model=ConsultaOut)
def obtener_consulta_endpoint(
    consulta_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
    user_client: Client = Depends(get_user_client),
) -> ConsultaOut:
    return obtener_consulta(user_client, consulta_id=consulta_id, drogueria_id=usuario.drogueria_id)


@router.get("/pcp/consultas/{consulta_id}/pdf")
def descargar_pdf_consulta_endpoint(
    consulta_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_LECTURA_PCP)),
) -> Response:
    pdf_bytes = generar_pdf_consulta_para_endpoint(
        consulta_id=consulta_id, drogueria_id=usuario.drogueria_id
    )
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/pcp/consultas/{consulta_id}/enviar", response_model=ConsultaOut)
def enviar_consulta_endpoint(
    consulta_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_ESCRITURA_PCP)),
) -> ConsultaOut:
    return enviar_consulta_para_endpoint(
        consulta_id=consulta_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id
    )
