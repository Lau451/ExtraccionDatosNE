"""Modelos de import legado de PCP (0012_pcp_extras.sql M3, design.md D8,
spec `pcp-legacy-import`).

El export legado es plano y desnormalizado: una fila por renglón, con los
13 campos de cabecera confirmados por el usuario (código/razón social del
cliente, número de PCP, número de presupuesto, proceso comercial, importe
total, ambas fechas) repetidos en cada fila que comparte el mismo "número de
PCP" (D8, "Confirmed export contract"). `FilaImportPcpLegacy` modela esa fila
tal cual llega -- el payload completo del import es una lista de estas.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

# D8: "1" = cotización directa, "2" = licitación. Ausente -> default
# `licitacion` (decisión confirmada por el usuario, no `cotizacion`).
ProcesoComercialLegacy = Literal["1", "2"]


class FilaImportPcpLegacy(BaseModel):
    """Una fila del export legado (13 columnas, D8). Los campos de cabecera
    (todo salvo `renglon`/`codigo_producto`/`descripcion_producto`/
    `cantidad_producto`/`precio_producto`) se repiten en cada fila que
    comparte `numero_pcp` -- el servicio usa la primera fila de cada grupo
    como cabecera (D8: "el header-level resolution ... se reusa para cada
    fila de renglón que lo comparte")."""

    codigo_cliente: str
    razon_social_cliente: str
    numero_pcp: str
    numero_presupuesto: str | None = None
    proceso_comercial: ProcesoComercialLegacy | None = None
    importe_total: Decimal | None = None
    fecha_generacion: str | None = None
    fecha_respuesta_esperada: str | None = None
    renglon: int
    codigo_producto: str | None = None
    descripcion_producto: str
    cantidad_producto: Decimal
    precio_producto: Decimal | None = None


class ImportPcpLegacyRequest(BaseModel):
    filas: list[FilaImportPcpLegacy]


class ImportPcpLegacyResultado(BaseModel):
    codigo_legacy: str
    pcp_id: str
    accion: Literal["creado", "actualizado"]
    renglones_procesados: int
