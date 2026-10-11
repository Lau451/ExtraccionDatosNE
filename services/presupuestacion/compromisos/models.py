from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class CompromisoEntrega(BaseModel):
    """Una fila de `v_compromisos_entregas` (0032): un ítem de una entrega abierta de una OC
    exportada a Progress."""

    drogueria_id: str
    orden_compra_id: str
    numero_oc: str
    version_numero: int | None = None
    exportado_at: datetime
    cliente: str | None = None
    entrega_oc_id: str
    numero_entrega: int
    fecha_entrega_planificada: date | None = None
    numero_renglon: int | None = None
    codigo_articulo: str | None = None
    descripcion: str | None = None
    cantidad_planificada: Decimal
    situacion: Literal["vencida", "futura"]
    dias_atraso: int
