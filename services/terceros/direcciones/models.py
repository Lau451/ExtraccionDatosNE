from typing import Literal

from pydantic import BaseModel

Uso = Literal["facturacion", "entrega", "documentacion", "otra"]


class TerceroDireccionCreate(BaseModel):
    etiqueta: str | None = None
    calle: str
    numero: str | None = None
    piso_depto: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    pais: str = "AR"
    observaciones: str | None = None


class TerceroDireccionUpdate(BaseModel):
    etiqueta: str | None = None
    calle: str | None = None
    numero: str | None = None
    piso_depto: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    pais: str | None = None
    observaciones: str | None = None
    activo: bool | None = None


class TerceroDireccionOut(BaseModel):
    id: str
    tercero_id: str
    drogueria_id: str
    etiqueta: str | None
    calle: str
    numero: str | None
    piso_depto: str | None
    ciudad: str | None
    provincia: str | None
    codigo_postal: str | None
    pais: str
    observaciones: str | None
    activo: bool


class DireccionUsoCreate(BaseModel):
    uso: Uso
    es_principal: bool = False


class DireccionUsoOut(BaseModel):
    id: str
    direccion_id: str
    tercero_id: str
    drogueria_id: str
    uso: str
    es_principal: bool
