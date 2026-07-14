from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.notificaciones.models import (
    NotificacionOut,
    NotificacionPreferenciaOut,
    NotificacionPreferenciaUpsert,
)
from services.presupuestacion.notificaciones.service import (
    listar_no_leidas,
    listar_preferencias,
    marcar_archivada_para_endpoint,
    marcar_leida_para_endpoint,
    upsert_preferencia,
)

router = APIRouter()


@router.get("/notificaciones/no-leidas", response_model=list[NotificacionOut])
def listar_no_leidas_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[NotificacionOut]:
    # user_client (no service_role): la policy no_sel de RLS ya permite
    # destinatario_id = auth.uid() -- RLS queda como red de contención real si el
    # filtro de destinatario_id del repository alguna vez se rompe.
    return listar_no_leidas(user_client, destinatario_id=usuario.id)


@router.patch("/notificaciones/{notificacion_id}/leer", response_model=NotificacionOut)
def marcar_leida_endpoint(
    notificacion_id: str, usuario: UsuarioPerfil = Depends(get_current_user)
) -> NotificacionOut:
    return marcar_leida_para_endpoint(notificacion_id=notificacion_id, usuario_id=usuario.id)


@router.patch("/notificaciones/{notificacion_id}/archivar", response_model=NotificacionOut)
def marcar_archivada_endpoint(
    notificacion_id: str, usuario: UsuarioPerfil = Depends(get_current_user)
) -> NotificacionOut:
    return marcar_archivada_para_endpoint(notificacion_id=notificacion_id, usuario_id=usuario.id)


@router.get("/notificacion-preferencias", response_model=list[NotificacionPreferenciaOut])
def listar_preferencias_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[NotificacionPreferenciaOut]:
    # user_client: la policy np_sel tiene la misma rama usuario_id = auth.uid().
    return listar_preferencias(user_client, usuario_id=usuario.id)


@router.put("/notificacion-preferencias", response_model=NotificacionPreferenciaOut)
def upsert_preferencia_endpoint(
    body: NotificacionPreferenciaUpsert,
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> NotificacionPreferenciaOut:
    # user_client: np_ins y np_upd permiten ambas usuario_id = auth.uid() (confirmado
    # contra las policies reales antes de migrar este endpoint puntual).
    return upsert_preferencia(
        user_client, usuario_id=usuario.id, drogueria_id=usuario.drogueria_id, body=body
    )
