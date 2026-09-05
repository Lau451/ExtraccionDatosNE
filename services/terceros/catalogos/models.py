from typing import Literal

from pydantic import BaseModel

TipoFormaPago = Literal["transferencia", "cheque", "echeq", "efectivo", "deposito", "otro"]


class SectorContactoCreate(BaseModel):
    nombre: str
    descripcion: str | None = None


class SectorContactoUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    activo: bool | None = None


class SectorContactoOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    descripcion: str | None
    activo: bool


class CondicionPagoCreate(BaseModel):
    nombre: str
    plazos_dias: list[int] = []
    descripcion: str | None = None


class CondicionPagoUpdate(BaseModel):
    nombre: str | None = None
    plazos_dias: list[int] | None = None
    descripcion: str | None = None
    activo: bool | None = None


class CondicionPagoOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    plazos_dias: list[int]
    descripcion: str | None
    activo: bool


class FormaPagoCreate(BaseModel):
    nombre: str
    tipo: TipoFormaPago = "otro"
    descripcion: str | None = None


class FormaPagoUpdate(BaseModel):
    nombre: str | None = None
    tipo: TipoFormaPago | None = None
    descripcion: str | None = None
    activo: bool | None = None


class FormaPagoOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    tipo: str
    descripcion: str | None
    activo: bool
