from typing import Any

from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError
from services.presupuestacion.notificaciones import repository as repo
from services.presupuestacion.notificaciones.models import CANALES_DEFAULT, NotificacionPreferenciaUpsert


def crear_notificacion(
    client: Client,
    *,
    drogueria_id: str,
    destinatario_id: str,
    tipo: str,
    titulo: str,
    mensaje: str | None = None,
    prioridad: str = "media",
    url_destino: str | None = None,
    origen: str = "sistema",
    relaciones: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Crea una notificación y una fila en notificacion_entregas por cada canal
    habilitado del destinatario para ese tipo. Sin preferencia cargada → default
    del backend (solo 'web'). Función de uso interno: la llaman otros módulos
    como efecto secundario (eventos, automatizaciones), no un endpoint público."""
    notificacion = repo.crear_notificacion(
        client,
        {
            "drogueria_id": drogueria_id,
            "destinatario_id": destinatario_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "prioridad": prioridad,
            "url_destino": url_destino,
            "origen": origen,
            "metadata": metadata,
            **(relaciones or {}),
        },
    )

    preferencias = repo.preferencias_de_tipo(client, usuario_id=destinatario_id, tipo=tipo)
    if preferencias:
        canales = [p["canal"] for p in preferencias if p["habilitada"]]
    else:
        canales = list(CANALES_DEFAULT)

    for canal in canales:
        repo.crear_entrega(
            client,
            {
                "notificacion_id": notificacion["id"],
                "drogueria_id": drogueria_id,
                "canal": canal,
                "estado": "pendiente",
            },
        )

    return notificacion


def listar_no_leidas(client: Client, *, destinatario_id: str) -> list[dict[str, Any]]:
    return repo.listar_no_leidas(client, destinatario_id=destinatario_id)


def marcar_leida(client: Client, *, notificacion_id: str, usuario_id: str) -> dict[str, Any]:
    notificacion = repo.obtener_notificacion(client, notificacion_id=notificacion_id)
    if notificacion is None:
        raise NotFoundError("No se encontró la notificación")
    if notificacion["destinatario_id"] != usuario_id:
        raise ForbiddenError("Solo el destinatario puede marcarla como leída")
    return repo.marcar_leida(client, notificacion_id=notificacion_id)


def marcar_archivada(client: Client, *, notificacion_id: str, usuario_id: str) -> dict[str, Any]:
    notificacion = repo.obtener_notificacion(client, notificacion_id=notificacion_id)
    if notificacion is None:
        raise NotFoundError("No se encontró la notificación")
    if notificacion["destinatario_id"] != usuario_id:
        raise ForbiddenError("Solo el destinatario puede archivarla")
    return repo.marcar_archivada(client, notificacion_id=notificacion_id)


def upsert_preferencia(
    client: Client, *, usuario_id: str, drogueria_id: str, body: NotificacionPreferenciaUpsert
) -> dict[str, Any]:
    return repo.upsert_preferencia(
        client,
        {
            "usuario_id": usuario_id,
            "drogueria_id": drogueria_id,
            "tipo": body.tipo,
            "canal": body.canal,
            "habilitada": body.habilitada,
        },
    )


def listar_preferencias(client: Client, *, usuario_id: str) -> list[dict[str, Any]]:
    return repo.listar_preferencias(client, usuario_id=usuario_id)


def marcar_leida_para_endpoint(*, notificacion_id: str, usuario_id: str) -> dict[str, Any]:
    return marcar_leida(get_service_client(), notificacion_id=notificacion_id, usuario_id=usuario_id)


def marcar_archivada_para_endpoint(*, notificacion_id: str, usuario_id: str) -> dict[str, Any]:
    return marcar_archivada(get_service_client(), notificacion_id=notificacion_id, usuario_id=usuario_id)
