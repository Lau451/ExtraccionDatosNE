from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.planes.models import PlanOut

router = APIRouter()


@router.get("/planes", response_model=list[PlanOut])
def listar_planes_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[PlanOut]:
    # Solo lectura: catálogo de planes, sin CRUD todavía (sin lógica de
    # facturación). RLS (planes_sel) ya permite SELECT a cualquier autenticado.
    return user_client.table("planes").select("*").eq("activo", True).order("nombre").execute().data
