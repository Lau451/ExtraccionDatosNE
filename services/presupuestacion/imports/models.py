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


# codigo_interno es obligatorio para ambos (a diferencia del esquema plano
# anterior, donde proveedores lo tenía opcional): terceros_legacy_map.codigo_legacy
# es NOT NULL (migración 0008), así que el RPC upsert_terceros_legacy no admite
# una fila sin código de origen legado (design.md sección 7).
#
# direccion/ciudad/provincia/codigo_postal/plazo_pago_dias/condiciones_pago se
# eliminan de ambos modelos: esos campos ya no viven en `clientes`/`proveedores`
# (se movieron a `tercero_direcciones` y a `condiciones_pago.plazos_dias`, FK-
# based) y el RPC upsert_terceros_legacy no los recibe ni los resuelve — quedan
# fuera del alcance del import legado en este change (design.md sección 7 no
# extiende el contrato del RPC para direcciones/condiciones de pago).
class ImportProveedorRow(BaseModel):
    codigo_interno: str
    razon_social: str
    cuit: str | None = None
    tipo: TipoProveedor | None = None
    es_competidor: bool | None = None
    es_proveedor_compra: bool | None = None


class ImportProveedoresRequest(BaseModel):
    proveedores: list[ImportProveedorRow]


class ImportProveedoresResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int


class ImportClienteRow(BaseModel):
    codigo_interno: str
    razon_social: str
    cuit: str | None = None
    tipo: TipoCliente | None = None


class ImportClientesRequest(BaseModel):
    clientes: list[ImportClienteRow]


class ImportClientesResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
