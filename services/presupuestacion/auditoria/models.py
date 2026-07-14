from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EntidadAuditable = Literal["proceso_comercial", "comparativa", "orden_compra", "presupuesto", "evento"]

_COLUMNA_FK_POR_ENTIDAD: dict[str, str] = {
    "proceso_comercial": "proceso_comercial_id",
    "comparativa": "comparativa_id",
    "orden_compra": "orden_compra_id",
    "presupuesto": "presupuesto_id",
    "evento": "evento_id",
}


class HistorialCambioOut(BaseModel):
    id: str
    tipo_cambio: str
    campo: str | None
    valor_anterior: str | None
    valor_nuevo: str | None
    batch_id: str | None
    usuario_id: str | None
    origen: str
    observaciones: str | None
    created_at: datetime
