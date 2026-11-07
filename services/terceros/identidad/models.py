from pydantic import BaseModel, ConfigDict


class TerceroUpdate(BaseModel):
    """Solo los campos que Progress no manda (docs/arquitectura/maestros-progress.md):
    codigo_interno, razon_social, cuit y activo los escribe la importación, y un body
    que los incluya responde 422."""

    model_config = ConfigDict(extra="forbid")

    nombre_fantasia: str | None = None
    email: str | None = None
    telefono: str | None = None
    sitio_web: str | None = None
    notas: str | None = None


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


class TerceroListOut(BaseModel):
    items: list[TerceroOut]
    total: int


class ClienteRolUpdate(BaseModel):
    """El rol lo crea la importación; la app solo fija la condición y forma de pago
    habitual (docs/arquitectura/maestros-progress.md)."""

    model_config = ConfigDict(extra="forbid")

    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ClienteRolOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool


class ProveedorRolUpdate(BaseModel):
    """Mismo criterio que ClienteRolUpdate: tipo, es_competidor, es_proveedor_compra y
    activo los escribe la importación."""

    model_config = ConfigDict(extra="forbid")

    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None


class ProveedorRolOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    es_competidor: bool
    es_proveedor_compra: bool
    condicion_pago_id: str | None
    forma_pago_id: str | None
    activo: bool
