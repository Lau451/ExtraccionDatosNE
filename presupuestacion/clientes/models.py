from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]
CategoriaObservacion = Literal[
    "general", "pago", "contacto", "logistica", "historial", "alerta", "otro"
]


class ClienteFormatoDocumentoUpsert(BaseModel):
    doc_type: DocType
    descripcion_estructura: str | None = None
    instrucciones_prompt: str | None = None
    archivo_ejemplo_path: str | None = None
    archivo_ejemplo_nombre: str | None = None
    activo: bool = True


class ClienteFormatoDocumentoOut(BaseModel):
    id: str
    cliente_id: str
    doc_type: DocType
    descripcion_estructura: str | None
    instrucciones_prompt: str | None
    archivo_ejemplo_path: str | None
    archivo_ejemplo_nombre: str | None
    activo: bool


class ClienteObservacionCreate(BaseModel):
    categoria: CategoriaObservacion = "general"
    observacion: str


class ClienteObservacionOut(BaseModel):
    id: str
    cliente_id: str
    categoria: CategoriaObservacion
    observacion: str
    creado_por: str | None
    created_at: datetime
