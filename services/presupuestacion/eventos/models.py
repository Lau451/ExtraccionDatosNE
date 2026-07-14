from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

TipoEvento = Literal[
    "compra", "recepcion", "entrega", "seguimiento", "reclamo", "facturacion", "pago",
    "llamada", "reunion", "recordatorio", "vencimiento", "observacion", "otro",
]
EstadoEvento = Literal["pendiente", "bloqueado", "en_progreso", "completado", "cancelado", "vencido"]
Prioridad = Literal["baja", "media", "alta", "urgente"]
OrigenEvento = Literal["usuario", "ia", "sistema", "automatico"]


class EventoCreate(BaseModel):
    tipo: TipoEvento
    titulo: str
    descripcion: str | None = None
    prioridad: Prioridad = "media"
    proceso_comercial_id: str | None = None
    comparativa_id: str | None = None
    orden_compra_id: str | None = None
    cliente_id: str | None = None
    proveedor_id: str | None = None
    responsable_id: str | None = None
    depende_de_id: str | None = None
    fecha_programada: datetime | None = None
    fecha_limite: datetime | None = None
    metadata: dict | None = None


class EventoUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    prioridad: Prioridad | None = None
    responsable_id: str | None = None
    fecha_programada: datetime | None = None
    fecha_limite: datetime | None = None
    estado: Literal["cancelado"] | None = None
    metadata: dict | None = None


class EventoOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    titulo: str
    descripcion: str | None
    estado: str
    prioridad: str
    origen: str
    proceso_comercial_id: str | None
    comparativa_id: str | None
    orden_compra_id: str | None
    cliente_id: str | None
    proveedor_id: str | None
    responsable_id: str | None
    depende_de_id: str | None
    evento_recurrente_id: str | None
    fecha_programada: datetime | None
    fecha_limite: datetime | None
    fecha_real: datetime | None
    metadata: dict | None


class EventoBloqueoOut(BaseModel):
    evento_id: str
    drogueria_id: str
    tipo: str
    titulo: str
    estado: str
    prioridad: str
    fecha_limite: datetime | None
    responsable_id: str | None
    depende_de_id: str | None
    depende_de: str | None
    estado_dependencia: str | None
    puede_avanzar: bool


class CalendarioItem(BaseModel):
    evento_id: str
    drogueria_id: str
    tipo: str
    titulo: str
    estado: str
    prioridad: str
    origen: str
    proceso_comercial_id: str | None
    cliente_id: str | None
    cliente: str | None
    responsable_id: str | None
    responsable: str | None
    fecha_programada: datetime | None
    fecha_limite: datetime | None
    fecha_real: datetime | None
    vencido: bool


class EventoRecurrenteCreate(BaseModel):
    tipo: TipoEvento
    titulo: str
    descripcion: str | None = None
    prioridad: Prioridad = "media"
    responsable_id: str | None = None
    cliente_id: str | None = None
    proveedor_id: str | None = None
    metadata: dict | None = None
    rrule: str
    fecha_inicio: date
    fecha_fin: date | None = None


class EventoRecurrenteUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    prioridad: Prioridad | None = None
    responsable_id: str | None = None
    rrule: str | None = None
    fecha_fin: date | None = None
    activa: bool | None = None


class EventoRecurrenteOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    titulo: str
    descripcion: str | None
    prioridad: str
    responsable_id: str | None
    cliente_id: str | None
    proveedor_id: str | None
    rrule: str
    fecha_inicio: date
    fecha_fin: date | None
    proxima_ejecucion: datetime | None
    ultima_generacion: datetime | None
    instancias_generadas: int
    activa: bool
