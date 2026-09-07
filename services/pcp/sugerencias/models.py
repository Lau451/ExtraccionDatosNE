"""Modelos de sugerencias de PCP (design.md D12, spec `pcp-sugerencias`).

D12: "las sugerencias son consultas, no tablas" -- no hay ninguna
persistencia nueva asociada a este módulo, solo los shapes de salida que
estos modelos formalizan para `response_model` de FastAPI.
"""

from decimal import Decimal

from pydantic import BaseModel


class SugerenciaAgrupacionOut(BaseModel):
    """Spec "Quantity-Grouping Suggestion". `pcp_ids`/`renglon_ids`
    identifican los PCPs/renglones involucrados -- surgir esta sugerencia
    nunca fusiona ni modifica ninguno de ellos (spec "Suggestion Never
    Auto-merges PCPs"): `services/pcp/sugerencias/service.py` es puramente de
    lectura, sin ningún código que escriba sobre `pcp`/`pcp_renglones`."""

    producto_id: str
    cantidad_agregada: Decimal
    pcp_ids: list[str]
    renglon_ids: list[str]


class SugerenciaPrecioRecienteOut(BaseModel):
    """Spec "Recent-Price-Reuse Suggestion". Espejo directo de las columnas
    que ya expone `v_precios_especiales_vigentes` (0012_pcp_extras.sql M6,
    vigente desde PR2) -- D12 pide reusar ese filtrado (`activa=true` +
    `mantenimiento_hasta >= CURRENT_DATE`), no reimplementarlo en Python."""

    precio_proveedor_id: str
    proveedor: str
    mantenimiento_hasta: str
    dias_restantes: int
    precio_unitario: Decimal
    cantidad_minima: Decimal | None
    cantidad_maxima: Decimal | None
