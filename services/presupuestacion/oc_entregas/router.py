from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.oc_entregas.models import (
    PlanificacionEntregasOut,
    PlanificarEntregasOut,
    PlanificarEntregasRequest,
)
from services.presupuestacion.oc_entregas.service import obtener_planificacion, planificar_entregas

router = APIRouter()

# Mismos roles que _ROLES_MATCHING (oc_presupuesto/router.py, D12): la
# planificación de entregas es la continuación natural de la pantalla de
# matching, no del registro de entregas físicas (compras/router.py::
# _ROLES_ENTREGA, que además incluye "compras" -- ese rol entrega
# físicamente, no planifica). Tupla local nueva, mismo criterio que el resto
# de los routers del backend (declarada acá, no importada).
_ROLES_ENTREGAS = ("admin", "gerencia", "lider_comercial", "comercial")


@router.get(
    "/ordenes-compra/{orden_compra_id}/entregas/planificacion",
    response_model=PlanificacionEntregasOut,
)
def planificacion_entregas_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ENTREGAS)),
) -> PlanificacionEntregasOut:
    # Corre con SERVICE client (ver el docstring de oc_entregas/repository.py):
    # la RLS de DELETE de entregas_oc/entregas_oc_items es solo-superadmin, así
    # que este módulo entero usa un único modelo de autorización -- el
    # aislamiento por droguería lo da el filtro explícito `drogueria_id`
    # dentro del service, no la RLS del user client.
    return obtener_planificacion(
        get_service_client(), orden_compra_id=orden_compra_id, drogueria_id=usuario.drogueria_id
    )


@router.put(
    "/ordenes-compra/{orden_compra_id}/entregas/planificacion",
    response_model=PlanificarEntregasOut,
)
def planificar_entregas_endpoint(
    orden_compra_id: str,
    body: PlanificarEntregasRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ENTREGAS)),
) -> PlanificarEntregasOut:
    return planificar_entregas(
        get_service_client(),
        orden_compra_id=orden_compra_id,
        drogueria_id=usuario.drogueria_id,
        usuario_id=usuario.id,
        entregas=body.entregas,
    )
