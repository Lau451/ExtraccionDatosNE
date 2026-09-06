"""Modelos del catálogo producto<->proveedor (0011_pcp_modelo.sql M3,
design.md D3, spec `pcp-catalogo-proveedores`).
"""

from pydantic import BaseModel


class ProductoProveedorCreate(BaseModel):
    """Alta de una asociación producto<->proveedor (spec "Ad-Hoc Supplier
    Addition During a PCP"). `producto_id` llega por la URL (recurso anidado
    bajo el producto), no por el body -- mismo criterio que `pcp_id` en
    `services/pcp/renglones/models.py::PcpRenglonCreate` / `tercero_id` en
    `TerceroDireccionCreate`: un id de tenant/entidad padre resuelto por el
    router nunca se confía al cliente."""

    proveedor_id: str
    codigo_proveedor: str | None = None
    preferido: bool = False
    notas: str | None = None


class ProductoProveedorOut(BaseModel):
    id: str
    drogueria_id: str
    producto_id: str
    proveedor_id: str
    codigo_proveedor: str | None
    preferido: bool
    activo: bool
    notas: str | None
