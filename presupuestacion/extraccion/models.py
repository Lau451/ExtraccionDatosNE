from typing import Literal

from pydantic import BaseModel

DocumentType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]


class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None


class ResultadoValidarExtraccion(BaseModel):
    extraction_id: str
    document_type: DocumentType
    proceso_comercial_id: str
    filas_creadas: int
    comparativa_id: str | None = None
    reemplazo_version_anterior: bool = False
