from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DocType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]
CategoriaObservacion = Literal[
    "general", "pago", "contacto", "logistica", "historial", "alerta", "otro"
]


class ClienteUpdate(BaseModel):
    """Solo campos de la app (docs/arquitectura/maestros-progress.md): nombre, cuit,
    tipo y activo los escribe la importación, y un body que los incluya responde 422."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    telefono: str | None = None
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ClienteOut(BaseModel):
    """Forma combinada tercero+rol (decisión de Fase 8, design.md deja esto
    abierto explícitamente): `GET /clientes` devuelve un único objeto plano
    con la identidad heredada de `terceros` y los campos del rol cliente ya
    fusionados, en vez de anidar `{"tercero": {...}, "rol": {...}}`. Se
    prefiere el shape plano para minimizar el cambio de contrato hacia los
    consumidores existentes de `ClienteOut` (mismo criterio que el shape
    previo a esta migración), a costa de que actualizar un campo de
    identidad y uno de rol en la misma llamada dispare dos escrituras
    internas (ver clientes/service.py::actualizar_cliente)."""

    id: str
    drogueria_id: str
    codigo_interno: str | None
    nombre: str
    cuit: str | None
    email: str | None
    telefono: str | None
    tipo: str
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool


class ClienteContactoCreate(BaseModel):
    nombre: str
    apellido: str | None = None
    sector_id: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    celular: str | None = None
    es_principal: bool = False
    notas: str | None = None


class ClienteContactoUpdate(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    sector_id: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    celular: str | None = None
    es_principal: bool | None = None
    notas: str | None = None
    activo: bool | None = None


class ClienteContactoOut(BaseModel):
    """`cliente_id` acá es el `tercero_id` de `terceros_contactos` -- el
    contacto vive en `services.terceros.contactos`, no en una tabla propia
    de `clientes/` (`cliente_contactos` fue eliminada por la migración
    0008)."""

    id: str
    cliente_id: str
    nombre: str
    apellido: str | None
    sector_id: str | None
    cargo: str | None
    email: str | None
    telefono: str | None
    celular: str | None
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
