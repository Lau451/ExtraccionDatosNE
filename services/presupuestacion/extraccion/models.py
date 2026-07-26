from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]

# D7 — mismo valor que frontend/constants.ts (Phase 6). Introducida acá porque
# GET .../filas (Phase 3) ya necesita el tope para decidir `editable`; Phase 4
# reusa esta misma constante para el chequeo de `filas` en el body de validar.
MAX_FILAS_EDITABLES = 500


class FilaLicitacionIn(BaseModel):
    """Mismos nombres de columna que el CSV de licitación/cotización."""

    model_config = ConfigDict(extra="forbid")
    item: str
    descripcion: str
    cantidad: str


class FilaComparativaIn(BaseModel):
    """Mismos nombres de columna que el CSV de comparativa."""

    model_config = ConfigDict(extra="forbid")
    renglon: str
    proveedor: str
    marca: str | None = None
    precio: str


class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None
    # None  -> materializa desde el CSV (comportamiento actual, retrocompatible)
    # lista -> materializa desde acá; el CSV en disco NO se toca (D2)
    filas: list[FilaLicitacionIn] | list[FilaComparativaIn] | None = Field(default=None)


class ResultadoValidarExtraccion(BaseModel):
    extraction_id: str
    document_type: DocumentType
    proceso_comercial_id: str
    filas_creadas: int
    comparativa_id: str | None = None
    reemplazo_version_anterior: bool = False


class ExtraccionResumen(BaseModel):
    id: str
    document_type: DocumentType
    source_filename: str
    row_count: int
    status: str
    validado: bool
    proceso_comercial_id: str | None
    proceso_comercial_nombre: str | None
    created_at: datetime


class FilasExtraccionOut(BaseModel):
    extraction_id: str
    document_type: DocumentType
    row_count: int
    filas_leidas: int
    editable: bool
    columnas: list[str]
    filas: list[dict[str, str]]
