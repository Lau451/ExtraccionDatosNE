from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

OrigenCosto = Literal["costo_estandar", "precio_especial"]
MetodoPrecio = Literal["mercado", "piso_margen", "margen_objetivo", "sin_precio"]


class DetalleCalculo(BaseModel):
    origen_mercado: bool
    precio_mediana: Decimal | None
    muestras: int | None
    ventana_meses: int
    descuento_aplicado_pct: Decimal | None
    piso_calculado: Decimal
    referencia_calculada: Decimal | None
    gano: MetodoPrecio


class ResultadoPricingItem(BaseModel):
    item_proceso_id: str
    producto_id: str | None
    costo_usado: Decimal | None
    origen_costo: OrigenCosto | None
    precio_proveedor_id: str | None
    mantenimiento_hasta_usado: date | None
    precio_unitario: Decimal | None
    cantidad_ofertada: Decimal | None
    precio_mercado_usado: Decimal | None
    regla_pricing_id: str | None
    metodo_precio: MetodoPrecio
    margen_resultante_pct: Decimal | None
    detalle_calculo: DetalleCalculo | None
    stock_verificado: bool
    stock_al_generar: Decimal | None


class ResultadoGenerarPresupuesto(BaseModel):
    presupuesto_id: str
    monto_total: Decimal
    cantidad_items: int
    items_sin_precio: int
    regenerado: bool
