from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Clasificacion = Literal[
    "medicamento", "descartable", "solucion", "nutricion",
    "equipamiento", "reactivo", "cosmetico", "otro",
]


class ProductoCreate(BaseModel):
    codigo_interno: str
    nombre: str
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    marca_id: str | None = None
    envase_id: str | None = None
    alicuota_iva: Decimal | None = None
    codigo_anmat: str | None = None


class ProductoUpdate(BaseModel):
    nombre: str | None = None
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    marca_id: str | None = None
    envase_id: str | None = None
    alicuota_iva: Decimal | None = None
    codigo_anmat: str | None = None
    activo: bool | None = None


class ProductoOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str
    nombre: str
    categoria_id: str | None
    clasificacion: str | None
    droga: str | None
    presentacion: str | None
    forma_farmaceutica: str | None
    marca_id: str | None
    envase_id: str | None
    alicuota_iva: Decimal | None
    codigo_anmat: str | None
    activo: bool


class CategoriaCreate(BaseModel):
    nombre: str
    descripcion: str | None = None


class CategoriaUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    activa: bool | None = None


class CategoriaOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    descripcion: str | None
    activa: bool


class MarcaCreate(BaseModel):
    nombre: str


class MarcaUpdate(BaseModel):
    nombre: str | None = None
    activa: bool | None = None


class MarcaOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    activa: bool


class EnvaseCreate(BaseModel):
    nombre: str


class EnvaseUpdate(BaseModel):
    nombre: str | None = None
    activa: bool | None = None


class EnvaseOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    activa: bool


class CaracteristicaCreate(BaseModel):
    nombre: str


class CaracteristicaUpdate(BaseModel):
    nombre: str | None = None
    activa: bool | None = None


class CaracteristicaOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    activa: bool


class ProductoCaracteristicaCreate(BaseModel):
    caracteristica_id: str


class ProductoCaracteristicaOut(BaseModel):
    id: str
    producto_id: str
    caracteristica_id: str


class CostoCreate(BaseModel):
    costo_unitario: Decimal
    fecha_desde: date


class CostoOut(BaseModel):
    id: str
    producto_id: str
    costo_unitario: Decimal
    fecha_desde: date
    fecha_hasta: date | None
    origen: str


class StockAjuste(BaseModel):
    deposito: str | None = None
    cantidad_disponible: Decimal


class StockOut(BaseModel):
    id: str
    producto_id: str
    deposito: str | None
    cantidad_disponible: Decimal
    cantidad_comprometida: Decimal
