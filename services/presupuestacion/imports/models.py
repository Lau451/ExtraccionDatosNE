from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Clasificacion = Literal[
    "medicamento", "descartable", "insumo", "equipamiento", "perfumeria", "otro"
]
TipoProveedor = Literal["laboratorio", "drogueria", "distribuidor", "cooperativa", "otro"]
TipoCliente = Literal["hospital", "obra_social", "municipio", "provincia", "nacional", "otro"]


class ImportProductoRow(BaseModel):
    codigo_interno: str
    nombre: str
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    laboratorio: str | None = None
    codigo_anmat: str | None = None
    datos_sistema: dict | None = None


class ImportProductosRequest(BaseModel):
    productos: list[ImportProductoRow]


class ImportProductosResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int


class ImportCostoRow(BaseModel):
    codigo_interno: str
    costo_unitario: Decimal
    fecha_desde: date


class ImportCostosRequest(BaseModel):
    costos: list[ImportCostoRow]


class ImportCostosResultado(BaseModel):
    nuevos: int
    actualizados: int
    sin_cambios: int
    no_encontrados: list[str]


class ImportStockRow(BaseModel):
    codigo_interno: str
    deposito: str | None = None
    cantidad_disponible: Decimal


class ImportStockRequest(BaseModel):
    stock: list[ImportStockRow]


class ImportStockResultado(BaseModel):
    upserted: int
    no_encontrados: list[str]


class ImportProveedorRow(BaseModel):
    codigo_interno: str | None = None
    razon_social: str
    nombre_comercial: str | None = None
    cuit: str | None = None
    tipo: TipoProveedor | None = None
    es_competidor: bool | None = None
    es_proveedor_compra: bool | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None


class ImportProveedoresRequest(BaseModel):
    proveedores: list[ImportProveedorRow]


class ImportProveedoresResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
    sin_codigo_interno: int


class ImportClienteRow(BaseModel):
    codigo_interno: str
    nombre: str | None = None
    tipo: TipoCliente | None = None
    direccion: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None


class ImportClientesRequest(BaseModel):
    clientes: list[ImportClienteRow]


class ImportClientesResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
