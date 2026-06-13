"""Schemas Pydantic v2 para Gestión de Licitaciones."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoLicitacion = Literal["descartables", "medicamentos", "soluciones", "panales", "formulas"]
ModalidadLicitacion = Literal["mail", "pliego"]
EstadoLicitacion = Literal["abierta", "en_evaluacion", "adjudicada", "cerrada"]
ComparativaEstadoSet = Literal["pedida"]
ComparativaEstadoDerivado = Literal["cargada", "pedida", "sin_comparativa"]


def _normalize_count(row: dict) -> dict:
    """Aplana archivos_count:[{count:N}] → int. Modifica el dict in-place."""
    raw = row.get("archivos_count")
    if isinstance(raw, list) and raw:
        row["archivos_count"] = raw[0].get("count", 0)
    elif raw is None:
        row["archivos_count"] = 0
    return row


class LicitacionBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=True,
    )

    nombre: str = Field(..., min_length=1, max_length=255)
    tipo: TipoLicitacion
    cliente: Optional[str] = Field(None, max_length=255)
    apertura: Optional[date] = None
    vencimiento: Optional[date] = None
    tipo_gestion: Optional[str] = Field(None, max_length=120)
    modalidad: ModalidadLicitacion = "mail"
    estado: EstadoLicitacion = "abierta"
    monto_estimado: Optional[Decimal] = Field(None, ge=0)
    notas: Optional[str] = None

    @model_validator(mode="after")
    def vencimiento_after_apertura(self) -> "LicitacionBase":
        if self.vencimiento and self.apertura and self.vencimiento < self.apertura:
            raise ValueError("vencimiento no puede ser anterior a apertura")
        return self


class LicitacionCreate(LicitacionBase):
    """Payload para POST /api/licitaciones."""
    apertura: date  # obligatorio — override del Optional en LicitacionBase


class LicitacionUpdate(BaseModel):
    """Payload para PATCH /api/licitaciones/{id}. Todos los campos opcionales."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=True,
    )

    nombre: Optional[str] = Field(None, min_length=1, max_length=255)
    tipo: Optional[TipoLicitacion] = None
    cliente: Optional[str] = Field(None, max_length=255)
    apertura: Optional[date] = None
    vencimiento: Optional[date] = None
    tipo_gestion: Optional[str] = Field(None, max_length=120)
    modalidad: Optional[ModalidadLicitacion] = None
    estado: Optional[EstadoLicitacion] = None
    monto_estimado: Optional[Decimal] = Field(None, ge=0)
    notas: Optional[str] = None
    comparativa_estado: Optional[ComparativaEstadoSet] = None

    def to_db_payload(self) -> dict:
        """Devuelve solo los campos seteados (excluye campos no enviados) para PATCH."""
        return self.model_dump(exclude_unset=True, mode="json")


class LicitacionOut(LicitacionBase):
    """Licitación completa con metadatos de sistema."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        use_enum_values=True,
    )

    id: UUID
    created_at: datetime
    updated_at: datetime
    archivos_count: int = 0


class ArchivoVinculado(BaseModel):
    """Archivo de extracción vinculado a una licitación."""
    model_config = ConfigDict(extra="ignore")

    id: UUID
    source_filename: str
    document_type: str
    client_id: str
    row_count: int
    status: str
    created_at: datetime


class LicitacionDetalle(LicitacionOut):
    """Licitación con lista de archivos vinculados."""
    archivos: List[ArchivoVinculado] = Field(default_factory=list)


class ExtractionResultUpdate(BaseModel):
    """Payload para PATCH /api/extraction-results/{id}. Todos los campos opcionales."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    licitacion_id: Optional[UUID] = None
    document_type: Optional[Literal["comparativa", "licitacion", "orden_compra"]] = None

    def to_db_payload(self) -> dict:
        return self.model_dump(exclude_unset=True, mode="json")


class ExtractionResultOut(ArchivoVinculado):
    """Extraction result con licitacion_id para respuesta del PATCH."""
    licitacion_id: Optional[UUID] = None


class LicitacionActiva(BaseModel):
    """Payload mínimo para el selector de upload."""
    id: UUID
    nombre: str
    tipo: TipoLicitacion


class LicitacionCalendario(BaseModel):
    """Vista calendario: licitación con comparativa_estado derivado en runtime."""
    model_config = ConfigDict(extra="ignore")

    id: UUID
    nombre: str
    tipo: TipoLicitacion
    apertura: Optional[date] = None
    vencimiento: Optional[date] = None
    estado: EstadoLicitacion
    comparativa_estado: ComparativaEstadoDerivado


class LicitacionListResponse(BaseModel):
    """Respuesta paginada del listado de licitaciones."""
    items: List[LicitacionOut]
    total: int
    page: int = 1
    page_size: int = 50
