from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class OrdenCompraItemRequest(BaseModel):
    numero_renglon: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    oferta_item_id: str | None = None
    producto_id: str | None = None


class CrearOrdenCompraRequest(BaseModel):
    proceso_comercial_id: str
    numero_oc: str
    fecha_emision: date | None = None
    fecha_entrega_estimada: date | None = None
    direccion_entrega: str | None = None
    notas: str | None = None
    items: list[OrdenCompraItemRequest]


class ResultadoOrdenCompra(BaseModel):
    orden_compra_id: str
    numero_oc: str
    estado: str
    monto_total: Decimal | None
    items_cantidad: int


class EntregaItemRequest(BaseModel):
    oc_item_id: str
    cantidad_entregada: Decimal
    cantidad_rechazada: Decimal = Decimal("0")
    motivo_rechazo: str | None = None
    lote: str | None = None
    vencimiento: date | None = None


class CrearEntregaRequest(BaseModel):
    fecha_entrega_planificada: date | None = None
    fecha_entrega_real: date | None = None
    observaciones: str | None = None
    items: list[EntregaItemRequest]


class ResultadoEntrega(BaseModel):
    entrega_id: str
    estado: str
    orden_compra_estado: str
