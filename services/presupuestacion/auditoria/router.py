from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.auditoria.models import _COLUMNA_FK_POR_ENTIDAD, EntidadAuditable, HistorialCambioOut
from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client

router = APIRouter()

_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/historial/{entidad}/{entidad_id}", response_model=list[HistorialCambioOut])
def listar_historial_endpoint(
    entidad: EntidadAuditable,
    entidad_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[HistorialCambioOut]:
    columna = _COLUMNA_FK_POR_ENTIDAD[entidad]
    return (
        user_client.table("historial_cambios")
        .select("*")
        .eq(columna, entidad_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )
