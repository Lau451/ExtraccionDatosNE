from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_capacidad
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.oc_resumen.models import OcResumenOut
from services.presupuestacion.oc_resumen.service import obtener_resumen

router = APIRouter()


@router.get("/ordenes-compra/{orden_compra_id}/resumen", response_model=OcResumenOut)
def resumen_oc_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("oc_resumen.leer")),
    user_client: Client = Depends(get_user_client),
) -> OcResumenOut:
    # USER client: RLS (`mismo_tenant`) aísla por droguería; el chequeo explícito
    # de `drogueria_id` en el service queda como defensa en profundidad.
    return obtener_resumen(
        user_client, orden_compra_id=orden_compra_id, drogueria_id=usuario.drogueria_id
    )
