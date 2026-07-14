from datetime import datetime
from typing import Literal

from pydantic import BaseModel

TipoNotificacion = Literal[
    "oc_creada", "evento_vencido", "evento_asignado", "ia_completada",
    "error_automatizacion", "comparativa_disponible", "presupuesto_aprobado",
    "presupuesto_pendiente", "proceso_por_vencer", "entrega_atrasada",
    "precio_por_vencer", "sistema", "otro",
]
Prioridad = Literal["baja", "media", "alta", "urgente"]
OrigenNotificacion = Literal["usuario", "ia", "automatizacion", "webhook", "api", "sistema"]
Canal = Literal["web", "email", "whatsapp", "sms", "push", "webhook"]

CANALES_DEFAULT: tuple[Canal, ...] = ("web",)


class NotificacionOut(BaseModel):
    id: str
    drogueria_id: str
    destinatario_id: str
    tipo: str
    titulo: str
    mensaje: str | None
    prioridad: str
    url_destino: str | None
    origen: str
    leida_at: datetime | None
    archivada_at: datetime | None
    created_at: datetime


class NotificacionPreferenciaUpsert(BaseModel):
    tipo: TipoNotificacion
    canal: Canal
    habilitada: bool = True


class NotificacionPreferenciaOut(BaseModel):
    id: str
    usuario_id: str
    tipo: str
    canal: str
    habilitada: bool
