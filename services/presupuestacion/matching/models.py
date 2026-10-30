from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

EstadoMatching = Literal["pendiente", "automatico", "sugerido", "confirmado", "sin_match"]
MetodoMatching = Literal["exact", "fuzzy", "embedding", "manual"]


class CandidatoMatching(BaseModel):
    producto_id: str
    confianza: Decimal
    metodo: MetodoMatching
    detalle_scoring: dict[str, Any] | None = None


class ResultadoMatchingItem(BaseModel):
    item_proceso_id: str
    producto_id: str | None
    alias_id: str | None
    estado_matching: EstadoMatching
    confianza_matching: Decimal | None
    candidatos: list[CandidatoMatching]


class ConfirmarMatchingRequest(BaseModel):
    producto_id: str


class ItemMatchingPendiente(BaseModel):
    item_proceso_id: str
    proceso_comercial_id: str
    proceso: str
    clase: str
    cliente_id: str | None
    cliente: str | None
    numero_renglon: int
    descripcion: str
    estado_matching: EstadoMatching
    confianza_matching: Decimal | None
    candidatos: int


class ProductoResumen(BaseModel):
    id: str
    nombre: str
    codigo_interno: str | None


class CandidatoRenglon(BaseModel):
    producto: ProductoResumen
    confianza: Decimal
    metodo: MetodoMatching
    elegido: bool


class RenglonMatching(BaseModel):
    item_proceso_id: str
    numero_renglon: int
    descripcion: str
    cantidad: Decimal
    estado_matching: EstadoMatching
    confianza_matching: Decimal | None
    producto: ProductoResumen | None
    candidatos: list[CandidatoRenglon]


class MatchingProceso(BaseModel):
    proceso_comercial_id: str
    nombre: str
    clase: str
    cliente: str | None
    renglones: list[RenglonMatching]


class ProcesoConMatchingPendiente(BaseModel):
    proceso_comercial_id: str
    proceso: str
    clase: str
    cliente: str | None
    pendientes: int
    sugeridos: int
