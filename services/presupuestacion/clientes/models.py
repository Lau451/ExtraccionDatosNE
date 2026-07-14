from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]
CategoriaObservacion = Literal[
    "general", "pago", "contacto", "logistica", "historial", "alerta", "otro"
]
TipoCliente = Literal["hospital", "obra_social", "municipio", "provincia", "nacional", "otro"]


class ClienteCreate(BaseModel):
    nombre: str
    tipo: TipoCliente
    direccion: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None


class ClienteUpdate(BaseModel):
    nombre: str | None = None
    tipo: TipoCliente | None = None
    direccion: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None
    activo: bool | None = None


class ClienteOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str | None
    nombre: str
    tipo: str
    direccion: str | None
    ciudad: str | None
    provincia: str | None
    codigo_postal: str | None
    plazo_pago_dias: int | None
    condiciones_pago: str | None
    activo: bool


class ClienteContactoCreate(BaseModel):
    nombre: str
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    es_principal: bool = False
    notas: str | None = None


class ClienteContactoUpdate(BaseModel):
    nombre: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    es_principal: bool | None = None
    notas: str | None = None
    activo: bool | None = None


class ClienteContactoOut(BaseModel):
    id: str
    cliente_id: str
    nombre: str
    cargo: str | None
    email: str | None
    telefono: str | None
    es_principal: bool
    notas: str | None
    activo: bool


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
