from typing import Literal

from pydantic import BaseModel

# D5: services/terceros/ nunca importa services.presupuestacion, así que estos
# Literal se redefinen acá en vez de reusar los de
# services.presupuestacion.clientes.models / catalogo.models (mismos valores,
# consumidores distintos hasta que la Fase 8 los haga apuntar a terceros.api).
TipoCliente = Literal["hospital", "obra_social", "municipio", "provincia", "nacional", "otro"]
TipoProveedor = Literal["laboratorio", "drogueria", "distribuidor", "cooperativa", "otro"]


class TerceroCreate(BaseModel):
    codigo_interno: str | None = None
    razon_social: str
    nombre_fantasia: str | None = None
    cuit: str | None = None
    email: str | None = None
    telefono: str | None = None
    sitio_web: str | None = None
    notas: str | None = None


class TerceroUpdate(BaseModel):
    codigo_interno: str | None = None
    razon_social: str | None = None
    nombre_fantasia: str | None = None
    cuit: str | None = None
    email: str | None = None
    telefono: str | None = None
    sitio_web: str | None = None
    notas: str | None = None
    activo: bool | None = None


class TerceroOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str | None
    razon_social: str
    nombre_fantasia: str | None
    cuit: str | None
    email: str | None
    telefono: str | None
    sitio_web: str | None
    notas: str | None
    activo: bool
    # Solo presentes en el listado (listar_terceros): evitan una consulta por fila
    # para saber si mostrar el badge Cliente/Proveedor/Ambos. `obtener_tercero` no
    # los completa — quien necesita el rol completo pide /terceros/{id}/clientes o
    # /terceros/{id}/proveedores.
    tiene_rol_cliente: bool = False
    tiene_rol_proveedor: bool = False


class ClienteRolCreate(BaseModel):
    tipo: TipoCliente = "otro"
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ClienteRolUpdate(BaseModel):
    tipo: TipoCliente | None = None
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None
    activo: bool | None = None


class ClienteRolOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool


class ProveedorRolCreate(BaseModel):
    tipo: TipoProveedor = "otro"
    es_competidor: bool = True
    es_proveedor_compra: bool = False
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ProveedorRolUpdate(BaseModel):
    tipo: TipoProveedor | None = None
    es_competidor: bool | None = None
    es_proveedor_compra: bool | None = None
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None
    activo: bool | None = None


class ProveedorRolOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    es_competidor: bool
    es_proveedor_compra: bool
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool
