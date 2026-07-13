from fastapi import APIRouter, Depends
from supabase import Client

from presupuestacion.core.auth import UsuarioPerfil, require_roles
from presupuestacion.core.database import get_user_client
from presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from presupuestacion.presupuestos.models import AjustarItemRequest, ResultadoPresupuesto
from presupuestacion.presupuestos.service import (
    ajustar_item_para_endpoint,
    aprobar_presupuesto_para_endpoint,
    presentar_presupuesto_para_endpoint,
)

router = APIRouter()

_ROLES_APROBAR = ("superadmin", "admin", "gerencia", "lider_comercial")
_ROLES_AJUSTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRESENTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")


def _validar_presupuesto_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, presupuesto_id: str
) -> None:
    resultado = (
        user_client.table("presupuestos")
        .select("id, drogueria_id")
        .eq("id", presupuesto_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró el presupuesto")

    presupuesto_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and presupuesto_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El presupuesto no pertenece a tu droguería")


def _validar_item_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, presupuesto_item_id: str
) -> None:
    resultado = (
        user_client.table("presupuesto_items")
        .select("id, drogueria_id")
        .eq("id", presupuesto_item_id)
        .limit(1)
        .execute()
    )
    if not resultado.data:
        raise NotFoundError("No se encontró el ítem del presupuesto")

    item_drogueria_id = resultado.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and item_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El ítem no pertenece a tu droguería")


@router.post("/presupuestos/{presupuesto_id}/aprobar", response_model=ResultadoPresupuesto)
def aprobar_endpoint(
    presupuesto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_APROBAR)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoPresupuesto:
    _validar_presupuesto_de_la_drogueria(user_client, usuario, presupuesto_id)
    return aprobar_presupuesto_para_endpoint(presupuesto_id=presupuesto_id, usuario_id=usuario.id)


@router.post("/presupuestos/{presupuesto_id}/presentar", response_model=ResultadoPresupuesto)
def presentar_endpoint(
    presupuesto_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_PRESENTAR)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoPresupuesto:
    _validar_presupuesto_de_la_drogueria(user_client, usuario, presupuesto_id)
    return presentar_presupuesto_para_endpoint(presupuesto_id=presupuesto_id, usuario_id=usuario.id)


@router.patch("/presupuesto-items/{item_id}")
def ajustar_item_endpoint(
    item_id: str,
    body: AjustarItemRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_AJUSTAR)),
    user_client: Client = Depends(get_user_client),
) -> dict:
    _validar_item_de_la_drogueria(user_client, usuario, item_id)
    return ajustar_item_para_endpoint(
        presupuesto_item_id=item_id,
        precio_unitario=body.precio_unitario,
        cantidad_ofertada=body.cantidad_ofertada,
        excluido=body.excluido,
        motivo_exclusion=body.motivo_exclusion,
        usuario_id=usuario.id,
    )
