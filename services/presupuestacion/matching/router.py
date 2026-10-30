from uuid import UUID

from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.matching.models import (
    ConfirmarMatchingRequest,
    ItemMatchingPendiente,
    MatchingProceso,
    ProcesoConMatchingPendiente,
    ResultadoMatchingItem,
)
from services.presupuestacion.matching.service import (
    confirmar_matching_para_endpoint,
    listar_procesos_con_matching_pendiente,
    marcar_sin_match_para_endpoint,
    obtener_matching_proceso,
)

router = APIRouter()

_ROLES_MATCHING = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")


def _validar_item_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, item_proceso_id: str
) -> None:
    item = (
        user_client.table("items_proceso")
        .select("id, drogueria_id")
        .eq("id", item_proceso_id)
        .limit(1)
        .execute()
    )
    if not item.data:
        raise NotFoundError("No se encontró el renglón")

    item_drogueria_id = item.data[0]["drogueria_id"]
    if usuario.rol != "superadmin" and item_drogueria_id != usuario.drogueria_id:
        raise ForbiddenError("El renglón no pertenece a tu droguería")


@router.post("/items/{item_id}/confirmar-matching", response_model=ResultadoMatchingItem)
def confirmar_matching_endpoint(
    item_id: str,
    body: ConfirmarMatchingRequest,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoMatchingItem:
    _validar_item_de_la_drogueria(user_client, usuario, item_id)
    return confirmar_matching_para_endpoint(
        item_proceso_id=item_id, producto_id=body.producto_id, usuario_id=usuario.id
    )


@router.post("/items/{item_id}/sin-match", response_model=ResultadoMatchingItem)
def sin_match_endpoint(
    item_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> ResultadoMatchingItem:
    _validar_item_de_la_drogueria(user_client, usuario, item_id)
    return marcar_sin_match_para_endpoint(item_proceso_id=item_id)


@router.get("/matching/pendientes", response_model=list[ItemMatchingPendiente])
def listar_pendientes_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> list[ItemMatchingPendiente]:
    resultado = user_client.table("v_matching_pendiente").select("*").execute()
    return resultado.data


@router.get("/matching/procesos", response_model=list[ProcesoConMatchingPendiente])
def listar_procesos_pendientes_endpoint(
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> list[ProcesoConMatchingPendiente]:
    return listar_procesos_con_matching_pendiente(user_client)


@router.get("/procesos-comerciales/{proceso_id}/matching", response_model=MatchingProceso)
def obtener_matching_proceso_endpoint(
    # UUID: a malformed id is a 422 here instead of a PostgREST error (500).
    proceso_id: UUID,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_MATCHING)),
    user_client: Client = Depends(get_user_client),
) -> MatchingProceso:
    return obtener_matching_proceso(
        user_client,
        proceso_comercial_id=str(proceso_id),
        drogueria_id=None if usuario.rol == "superadmin" else usuario.drogueria_id,
    )
