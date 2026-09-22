from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.oc_presupuesto.models import (
    ConfirmarVinculoRequest,
    MatchingOut,
    PresupuestosCandidatosOut,
)
from services.presupuestacion.oc_presupuesto.service import (
    confirmar_vinculo,
    descartar_renglon,
    deshacer_vinculo,
    obtener_matching,
    rankear_presupuestos_candidatos,
)

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


@router.get("/ordenes-compra/{orden_compra_id}/matching", response_model=MatchingOut)
def matching_endpoint(
    orden_compra_id: str,
    presupuesto_id: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> MatchingOut:
    # presupuesto_id es opcional (D13): si falta, obtener_matching lo resuelve
    # (D8) y lo devuelve en la respuesta.
    return obtener_matching(
        user_client,
        orden_compra_id=orden_compra_id,
        drogueria_id=usuario.drogueria_id,
        presupuesto_id=presupuesto_id,
    )


@router.post(
    "/ordenes-compra/{orden_compra_id}/items/{oc_item_id}/vinculo", response_model=MatchingOut
)
def confirmar_vinculo_endpoint(
    orden_compra_id: str,
    oc_item_id: str,
    body: ConfirmarVinculoRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> MatchingOut:
    # C3: oci_upd ya permite UPDATE a _ROLES_MATCHING -- corre con el USER
    # client, igual que las lecturas; sin service client (D12).
    return confirmar_vinculo(
        user_client,
        orden_compra_id=orden_compra_id,
        oc_item_id=oc_item_id,
        presupuesto_item_id=body.presupuesto_item_id,
        drogueria_id=usuario.drogueria_id,
        usuario_id=usuario.id,
    )


@router.delete(
    "/ordenes-compra/{orden_compra_id}/items/{oc_item_id}/vinculo", response_model=MatchingOut
)
def deshacer_vinculo_endpoint(
    orden_compra_id: str,
    oc_item_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> MatchingOut:
    return deshacer_vinculo(
        user_client,
        orden_compra_id=orden_compra_id,
        oc_item_id=oc_item_id,
        drogueria_id=usuario.drogueria_id,
    )


@router.post(
    "/ordenes-compra/{orden_compra_id}/items/{oc_item_id}/descartar", response_model=MatchingOut
)
def descartar_renglon_endpoint(
    orden_compra_id: str,
    oc_item_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> MatchingOut:
    return descartar_renglon(
        user_client,
        orden_compra_id=orden_compra_id,
        oc_item_id=oc_item_id,
        drogueria_id=usuario.drogueria_id,
    )
