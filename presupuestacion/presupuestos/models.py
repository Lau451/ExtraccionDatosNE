from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

EstadoPresupuesto = Literal[
    "generado", "en_revision", "aprobado", "presentado", "adjudicado", "rechazado", "vencido"
]


class AjustarItemRequest(BaseModel):
    precio_unitario: Decimal | None = None
    cantidad_ofertada: Decimal | None = None
    excluido: bool | None = None
    motivo_exclusion: str | None = None


class ResultadoPresupuestoItem(BaseModel):
    id: str
    precio_unitario: Decimal | None
    cantidad_ofertada: Decimal | None
    monto_total: Decimal | None
    metodo_precio: str | None
    margen_resultante_pct: Decimal | None
    precio_original_motor: Decimal | None
    excluido: bool
    motivo_exclusion: str | None


class ResultadoPresupuesto(BaseModel):
    presupuesto_id: str
    estado: EstadoPresupuesto
    monto_total: Decimal | None
    cantidad_items: int
    items_sin_precio: int
