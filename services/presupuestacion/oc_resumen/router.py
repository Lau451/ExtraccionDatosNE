from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.oc_resumen.models import OcResumenOut
from services.presupuestacion.oc_resumen.service import obtener_resumen

router = APIRouter()

# Mismos roles de lectura que compromisos/router.py::_ROLES_LECTURA (tupla local,
# declarada acá y no importada, mismo criterio que el resto de los routers).
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/ordenes-compra/{orden_compra_id}/resumen", response_model=OcResumenOut)
def resumen_oc_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
) -> OcResumenOut:
    # SERVICE client (como oc_entregas): el aislamiento por droguería lo da el
    # filtro explícito `drogueria_id` dentro del service.
    return obtener_resumen(
        get_service_client(), orden_compra_id=orden_compra_id, drogueria_id=usuario.drogueria_id
    )
