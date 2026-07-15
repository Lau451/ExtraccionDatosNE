from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Clase = Literal["cotizacion", "licitacion"]
Modalidad = Literal["mail", "pliego"]
Estado = Literal[
    "abierto",
    "presupuestado",
    "presentado",
    "en_evaluacion",
    "adjudicado",
    "perdido",
    "cerrado",
    "cancelado",
]


class ProcesoComercialCreate(BaseModel):
    nombre: str
    clase: Clase
    cliente_id: str | None = None
    categoria_id: str | None = None
    monto_estimado: Decimal | None = None
    notas: str | None = None
    apertura: date | None = None
    vencimiento: date | None = None
    tipo_gestion: str | None = None
    modalidad: Modalidad | None = None
    comparativa_pedida: bool = False


class ProcesoComercialOut(BaseModel):
    id: str
    drogueria_id: str
    cliente_id: str | None
    clase: Clase
    nombre: str
    categoria_id: str | None
    fecha: date
    estado: Estado
    monto_estimado: Decimal | None
    notas: str | None
    apertura: date | None
    vencimiento: date | None
    tipo_gestion: str | None
    modalidad: Modalidad | None
    comparativa_pedida: bool
    created_at: datetime
    updated_at: datetime
