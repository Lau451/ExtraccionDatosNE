from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EntidadObjetivo = Literal[
    "proceso_comercial", "comparativa", "orden_compra", "presupuesto",
    "evento", "extraction_result", "entrega",
]
TipoAccion = Literal[
    "crear_evento", "crear_oc", "enviar_notificacion", "enviar_email",
    "enviar_whatsapp", "ejecutar_agente_ia", "cambiar_estado", "webhook",
]
ModoEjecucion = Literal["inmediato", "cola"]


class ReglaAutomatizacionCreate(BaseModel):
    nombre: str
    descripcion: str | None = None
    evento_disparador: str
    entidad_objetivo: EntidadObjetivo
    condicion: dict | None = None
    tipo_accion: TipoAccion
    parametros_accion: dict | None = None
    modo_ejecucion: ModoEjecucion = "cola"
    max_reintentos: int = 3
    prioridad: int = 0


class ReglaAutomatizacionUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    condicion: dict | None = None
    parametros_accion: dict | None = None
    modo_ejecucion: ModoEjecucion | None = None
    max_reintentos: int | None = None
    prioridad: int | None = None
    activa: bool | None = None


class ReglaAutomatizacionOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    descripcion: str | None
    evento_disparador: str
    entidad_objetivo: str
    condicion: dict | None
    tipo_accion: str
    parametros_accion: dict | None
    modo_ejecucion: str
    max_reintentos: int
    prioridad: int
    activa: bool


class MetricaAutomatizacionOut(BaseModel):
    regla_id: str
    drogueria_id: str
    nombre: str
    tipo_accion: str
    modo_ejecucion: str
    ejecuciones: int
    exitosas: int
    fallidas: int
    duracion_promedio_ms: float | None
    duracion_max_ms: int | None
    intentos_promedio: float | None
    ultima_ejecucion: datetime | None
