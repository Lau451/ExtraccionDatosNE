from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.extraccion.models import ResultadoValidarExtraccion, ValidarExtraccionRequest
from services.presupuestacion.extraccion.service import validar_extraccion_para_endpoint

router = APIRouter()

_ROLES_VALIDAR = ("admin", "gerencia", "lider_comercial", "comercial")


@router.post("/extracciones/{extraction_id}/validar", response_model=ResultadoValidarExtraccion)
def validar_extraccion_endpoint(
    extraction_id: str,
    body: ValidarExtraccionRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_VALIDAR)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoValidarExtraccion:
    resultado = (
        user_client.table("extraction_results")
        .select("id, drogueria_id")
        .eq("id", extraction_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró la extracción")

    extraccion_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and extraccion_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("La extracción no pertenece a tu droguería")

    return validar_extraccion_para_endpoint(
        extraction_id=extraction_id,
        usuario_id=usuario.id,
        proceso_comercial_id=body.proceso_comercial_id,
    )
