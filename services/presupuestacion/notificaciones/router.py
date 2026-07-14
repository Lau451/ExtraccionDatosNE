from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user
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
from services.presupuestacion.core.database import get_service_client

router = APIRouter()


@router.get("/notificaciones/no-leidas", response_model=list[NotificacionOut])
def listar_no_leidas_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
) -> list[NotificacionOut]:
    return listar_no_leidas(get_service_client(), destinatario_id=usuario.id)


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
) -> list[NotificacionPreferenciaOut]:
    return listar_preferencias(get_service_client(), usuario_id=usuario.id)


@router.put("/notificacion-preferencias", response_model=NotificacionPreferenciaOut)
def upsert_preferencia_endpoint(
    body: NotificacionPreferenciaUpsert, usuario: UsuarioPerfil = Depends(get_current_user)
) -> NotificacionPreferenciaOut:
    return upsert_preferencia(
        get_service_client(), usuario_id=usuario.id, drogueria_id=usuario.drogueria_id, body=body
    )
