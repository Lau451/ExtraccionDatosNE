from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.pricing.models import ResultadoGenerarPresupuesto
from services.presupuestacion.pricing.service import generar_presupuesto_para_endpoint

router = APIRouter()

_ROLES_GENERAR_PRESUPUESTO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRECIOS_ESPECIALES = ("superadmin", "admin", "gerencia", "compras")


@router.post("/procesos/{proceso_id}/generar-presupuesto", response_model=ResultadoGenerarPresupuesto)
def generar_presupuesto_endpoint(
    proceso_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_GENERAR_PRESUPUESTO)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoGenerarPresupuesto:
    proceso = (
        user_client.table("procesos_comerciales")
        .select("id, drogueria_id")
        .eq("id", proceso_id)
        .limit(1)
        .execute()
    )
    if not proceso.data:
        raise NotFoundError("No se encontró el proceso comercial")

    proceso_drogueria_id = proceso.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and proceso_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El proceso no pertenece a tu droguería")

    return generar_presupuesto_para_endpoint(
        proceso_comercial_id=proceso_id,
        drogueria_id=proceso_drogueria_id,
        disparado_por=usuario.id,
    )


@router.get("/precios-especiales")
def precios_especiales_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_PRECIOS_ESPECIALES)),
    user_client: Client = Depends(get_user_client),
) -> list[dict]:
    return user_client.table("v_precios_especiales_vigentes").select("*").execute().data
