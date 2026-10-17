from datetime import date

from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.compromisos import service
from services.presupuestacion.compromisos.models import CompromisoEntrega, ProximaFecha
from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client

router = APIRouter()

_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/compromisos-entregas", response_model=list[CompromisoEntrega])
def compromisos_entregas_endpoint(
    desde: date | None = None,
    hasta: date | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[CompromisoEntrega]:
    # Cliente del usuario: la vista es security_invoker, aplica su RLS.
    return service.listar_compromisos(
        user_client, drogueria_id=usuario.drogueria_id, desde=desde, hasta=hasta
    )


@router.get("/compromisos-entregas/proxima-fecha", response_model=ProximaFecha)
def proxima_fecha_endpoint(
    despues_de: date,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> ProximaFecha:
    fecha = service.proxima_fecha(user_client, drogueria_id=usuario.drogueria_id, despues_de=despues_de)
    return ProximaFecha(fecha=fecha)
