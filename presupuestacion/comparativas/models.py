from decimal import Decimal

from pydantic import BaseModel


class AsignarProveedorRequest(BaseModel):
    proveedor_id: str


class RenglonGanado(BaseModel):
    proceso_comercial_id: str
    proceso: str
    cliente: str | None
    oferta_item_id: str
    renglon_id: str | None
    descripcion: str | None
    precio_unitario: Decimal
    cantidad_ofertada: Decimal | None
    ganado_oficial: bool
    ganado_estimado: bool
    nivel: str | None


class OfertaSinMatchear(BaseModel):
    texto_crudo: str
    drogueria_id: str
    apariciones: int
    veces_ganador: int
