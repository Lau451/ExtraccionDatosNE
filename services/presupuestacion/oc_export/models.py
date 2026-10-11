# Modelos de entrada del módulo oc_export (openspec/changes/oc-export-progress, D4).
# Los consume `filas.construir_filas`; el repository (Fase 3) los arma desde la BD.
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class OcExport(BaseModel):
    """Cabecera de la OC que se repite en cada fila del CSV."""

    id: str
    numero_oc: str
    version_numero: int
    fecha_emision: date | None = None
    direccion_entrega: str | None = None


class RenglonExport(BaseModel):
    oc_item_id: str
    numero_renglon: int
    codigo_articulo: str | None = None
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal


class EntregaExport(BaseModel):
    """Una línea de entrega: cantidad planificada de un renglón en una entrega."""

    oc_item_id: str
    numero_entrega: int
    fecha_entrega: date
    cantidad_planificada: Decimal


class ResultadoExportacion(BaseModel):
    """Respuesta de `POST /ordenes-compra/{id}/exportar-progress` (D10)."""

    archivo: str
    exportado_at: datetime
    exportado_por: UUID
    filas: int
