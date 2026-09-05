from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Clasificacion = Literal[
    "medicamento", "descartable", "insumo", "equipamiento", "perfumeria", "otro"
]
TipoProveedor = Literal["laboratorio", "drogueria", "distribuidor", "cooperativa", "otro"]


class ProductoCreate(BaseModel):
    codigo_interno: str
    nombre: str
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    laboratorio: str | None = None
    codigo_anmat: str | None = None


class ProductoUpdate(BaseModel):
    nombre: str | None = None
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    laboratorio: str | None = None
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
    laboratorio: str | None
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


class ProveedorCreate(BaseModel):
    """Wrapper de compatibilidad (design.md D2/D5, Fase 8): la identidad y
    el rol proveedor viven en `services.terceros.api` (terceros + rol
    proveedor) desde la migración 0008 -- `catalogo/` ya no posee la tabla
    `proveedores`. Se conserva este wrapper, en vez de repuntar a los
    callers directo a `services.terceros.api`, porque `POST /proveedores`
    es un endpoint público existente y el CRUD completo (crear tercero +
    asignar rol en una sola llamada) es exactamente lo que necesitan sus
    consumidores actuales. `plazo_pago_dias`/`condiciones_pago` (texto
    libre) se reemplazan por `condicion_pago_id`/`forma_pago_id` (FK a los
    catálogos de `services.terceros.catalogos`, D1/D2)."""

    razon_social: str
    nombre_comercial: str | None = None
    cuit: str | None = None
    tipo: TipoProveedor = "otro"
    es_competidor: bool = True
    es_proveedor_compra: bool = False
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ProveedorUpdate(BaseModel):
    razon_social: str | None = None
    nombre_comercial: str | None = None
    cuit: str | None = None
    tipo: TipoProveedor | None = None
    es_competidor: bool | None = None
    es_proveedor_compra: bool | None = None
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None
    activo: bool | None = None


class ProveedorOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str | None
    razon_social: str
    nombre_comercial: str | None
    cuit: str | None
    tipo: str
    es_competidor: bool
    es_proveedor_compra: bool
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool


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
