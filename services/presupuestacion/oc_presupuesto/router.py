from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.oc_presupuesto.models import PresupuestosCandidatosOut
from services.presupuestacion.oc_presupuesto.service import rankear_presupuestos_candidatos

router = APIRouter()

# D12: tupla local nueva, mismo valor que _ROLES_VALIDAR (extraccion/router.py)
# y _ROLES_OC (compras/router.py) por el mismo criterio -- "escribe quien
# valida, no quien entrega" -- pero declarada acá (no importada de otro
# módulo) por el mismo patrón que ya usan todos los routers del backend.
# Desviación explícita respecto de D12 del cambio padre ("cero tuplas
# nuevas"): ver design.md D12.
_ROLES_MATCHING = ("admin", "gerencia", "lider_comercial", "comercial")


@router.get(
    "/ordenes-compra/{orden_compra_id}/presupuestos-candidatos",
    response_model=PresupuestosCandidatosOut,
)
def presupuestos_candidatos_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> PresupuestosCandidatosOut:
    # Autorización por endpoint (D12): require_roles ya corrió; la lectura de
    # la OC con el USER client vive dentro del service (D13 firma), y su RLS
    # ya filtra por tenant -- un 404 acá no confirma la existencia de una OC
    # de otra droguería.
    return rankear_presupuestos_candidatos(
        user_client, orden_compra_id=orden_compra_id, drogueria_id=usuario.drogueria_id
    )
