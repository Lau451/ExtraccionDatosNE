from pydantic import BaseModel


class TerceroContactoCreate(BaseModel):
    nombre: str
    apellido: str | None = None
    sector_id: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    celular: str | None = None
    es_principal: bool = False
    notas: str | None = None


class TerceroContactoUpdate(BaseModel):
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


class TerceroContactoOut(BaseModel):
    id: str
    tercero_id: str
    drogueria_id: str
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
