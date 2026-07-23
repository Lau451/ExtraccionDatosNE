import re

from pydantic import BaseModel, field_validator

_CUIT_RE = re.compile(r"^\d{2}-\d{8}-\d$")


def _validar_formato_cuit(valor: str) -> str:
    if not _CUIT_RE.match(valor):
        raise ValueError("El CUIT/CUIL debe tener el formato NN-NNNNNNNN-N")
    return valor


class DrogueriaCreate(BaseModel):
    nombre: str
    razon_social: str
    cuit: str
    ciudad: str
    provincia: str
    codigo_postal: str | None = None
    contacto_email: str
    contacto_telefono: str

    _validar_cuit = field_validator("cuit")(_validar_formato_cuit)


class DrogueriaUpdate(BaseModel):
    nombre: str | None = None
    razon_social: str | None = None
    cuit: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
    activa: bool | None = None
    plan_id: str | None = None

    @field_validator("cuit")
    @classmethod
    def _validar_cuit(cls, valor: str | None) -> str | None:
        if valor is None:
            return valor
        return _validar_formato_cuit(valor)


class DrogueriaOut(BaseModel):
    id: str
    nombre: str
    razon_social: str
    cuit: str
    ciudad: str
    provincia: str
    codigo_postal: str | None
    contacto_email: str
    contacto_telefono: str
    activa: bool
    plan_id: str | None
