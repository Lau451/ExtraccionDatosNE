# Modelos del módulo oc_resumen (odd/tasks/oc-resumen.md, T1): pantalla de
# resumen de solo lectura de una OC. Reusa los modelos de oc_entregas para la
# marca de exportación y el plan de entregas en vez de duplicarlos.
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from services.presupuestacion.oc_entregas.models import EntregaPlanOut, ExportacionOut
from services.presupuestacion.oc_presupuesto.models import EstadoVinculo


class ClienteResumen(BaseModel):
    razon_social: str
    cuit: str | None = None


class ProductoResumen(BaseModel):
    codigo_interno: str | None = None
    nombre: str


class RenglonResumen(BaseModel):
    oc_item_id: str
    numero_renglon: int
    numero_renglon_documento: str | None = None
    descripcion: str
    producto: ProductoResumen | None = None
    cantidad: Decimal
    precio_unitario: Decimal | None = None
    monto_total: Decimal | None = None
    estado_vinculo: EstadoVinculo


class OcResumenOut(BaseModel):
    orden_compra_id: str
    numero_oc: str
    # None cuando la OC se ancla a un proceso comercial sin cliente (ck_oc_anclaje).
    cliente: ClienteResumen | None = None
    fecha_emision: date | None = None
    fecha_entrega_estimada: date | None = None
    direccion_entrega: str | None = None
    notas: str | None = None
    estado: str
    version_numero: int | None = None
    monto_total: Decimal | None = None
    exportacion: ExportacionOut | None = None
    renglones: list[RenglonResumen]
    entregas: list[EntregaPlanOut]
