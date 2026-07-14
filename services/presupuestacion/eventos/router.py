from fastapi import APIRouter, Depends
from supabase import Client

from services.presupuestacion.core.auth import UsuarioPerfil, require_roles
from services.presupuestacion.core.database import get_user_client
from services.presupuestacion.eventos.models import (
    CalendarioItem,
    EventoBloqueoOut,
    EventoCreate,
    EventoOut,
    EventoRecurrenteCreate,
    EventoRecurrenteOut,
    EventoRecurrenteUpdate,
    EventoUpdate,
)
from services.presupuestacion.eventos.service import (
    actualizar_evento_para_endpoint,
    actualizar_evento_recurrente_para_endpoint,
    calendario,
    completar_evento_para_endpoint,
    crear_evento_para_endpoint,
    crear_evento_recurrente_para_endpoint,
    eliminar_evento_para_endpoint,
    listar_eventos,
    listar_eventos_recurrentes,
    obtener_bloqueo,
    obtener_evento,
)

router = APIRouter()

_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")


@router.get("/eventos", response_model=list[EventoOut])
def listar_eventos_endpoint(
    estado: str | None = None,
    proceso_comercial_id: str | None = None,
    responsable_id: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[EventoOut]:
    return listar_eventos(
        user_client,
        drogueria_id=usuario.drogueria_id,
        estado=estado,
        proceso_comercial_id=proceso_comercial_id,
        responsable_id=responsable_id,
    )


@router.post("/eventos", response_model=EventoOut)
def crear_evento_endpoint(
    body: EventoCreate, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA))
) -> EventoOut:
    return crear_evento_para_endpoint(drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id)


@router.get("/eventos/{evento_id}", response_model=EventoOut)
def obtener_evento_endpoint(
    evento_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> EventoOut:
    return obtener_evento(user_client, evento_id=evento_id, drogueria_id=usuario.drogueria_id)


@router.patch("/eventos/{evento_id}", response_model=EventoOut)
def actualizar_evento_endpoint(
    evento_id: str, body: EventoUpdate, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA))
) -> EventoOut:
    return actualizar_evento_para_endpoint(
        evento_id=evento_id, drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.post("/eventos/{evento_id}/completar", response_model=EventoOut)
def completar_evento_endpoint(
    evento_id: str, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA))
) -> EventoOut:
    return completar_evento_para_endpoint(
        evento_id=evento_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id
    )


@router.delete("/eventos/{evento_id}", status_code=204)
def eliminar_evento_endpoint(
    evento_id: str, usuario: UsuarioPerfil = Depends(require_roles("admin", "gerencia"))
) -> None:
    eliminar_evento_para_endpoint(evento_id=evento_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id)


@router.get("/eventos/{evento_id}/bloqueo", response_model=EventoBloqueoOut)
def obtener_bloqueo_endpoint(
    evento_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> EventoBloqueoOut:
    return obtener_bloqueo(user_client, evento_id=evento_id, drogueria_id=usuario.drogueria_id)


@router.get("/calendario", response_model=list[CalendarioItem])
def calendario_endpoint(
    desde: str | None = None,
    hasta: str | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[CalendarioItem]:
    return calendario(user_client, drogueria_id=usuario.drogueria_id, desde=desde, hasta=hasta)


@router.get("/eventos-recurrentes", response_model=list[EventoRecurrenteOut])
def listar_eventos_recurrentes_endpoint(
    activa: bool | None = None,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[EventoRecurrenteOut]:
    return listar_eventos_recurrentes(user_client, drogueria_id=usuario.drogueria_id, activa=activa)


@router.post("/eventos-recurrentes", response_model=EventoRecurrenteOut)
def crear_evento_recurrente_endpoint(
    body: EventoRecurrenteCreate, usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA))
) -> EventoRecurrenteOut:
    return crear_evento_recurrente_para_endpoint(
        drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id
    )


@router.patch("/eventos-recurrentes/{evento_recurrente_id}", response_model=EventoRecurrenteOut)
def actualizar_evento_recurrente_endpoint(
    evento_recurrente_id: str,
    body: EventoRecurrenteUpdate,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_ESCRITURA)),
) -> EventoRecurrenteOut:
    return actualizar_evento_recurrente_para_endpoint(
        evento_recurrente_id=evento_recurrente_id,
        drogueria_id=usuario.drogueria_id,
        body=body,
        usuario_id=usuario.id,
    )
