from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from services.productos.models import ProductoOut

# D2/D11 (openspec/changes/gestor-pcp/design.md) -- discriminadores del
# renglón (0011_pcp_modelo.sql M2 ck_pcpr_origen/ck_pcpr_estado). No confundir
# con `services.pcp.gestion.models.OrigenPcp` -- ese es el origen del PCP en
# sí, este es por renglón (spec pcp-renglones, "Origen Discriminator on
# Renglón Selection").
OrigenRenglon = Literal["manual", "regla", "import_legado"]
EstadoRenglon = Literal["pendiente", "resuelto", "descartado"]


class PcpRenglonCreate(BaseModel):
    """Alta de un renglón (spec pcp-renglones, "Renglón Identity Anchored on
    item_proceso_id"). `pcp_id` llega por la URL (recurso anidado, mismo
    criterio que `TerceroDireccionCreate`/`tercero_id`), no por el body.

    `model_config = ConfigDict(extra="forbid")` es deliberado: la spec exige
    rechazar una request que identifique el renglón "solo por
    presupuesto_items.id" (spec, "Reject a renglón referencing
    presupuesto_items.id"). Este modelo ni siquiera define ese campo -- no
    hay ningún code path que lo acepte -- así que cualquier intento de
    pasarlo (con o sin `item_proceso_id` también presente) es rechazado por
    Pydantic antes de llegar a la capa de servicio, en vez de ser ignorado
    en silencio.
    """

    model_config = ConfigDict(extra="forbid")

    item_proceso_id: str
    origen: OrigenRenglon = "manual"
    regla_pcp_id: str | None = None


class PcpRenglonOut(BaseModel):
    id: str
    drogueria_id: str
    pcp_id: str
    item_proceso_id: str
    producto_id: str | None
    cantidad: Decimal | None
    precio_referencia: Decimal | None
    origen: str
    regla_pcp_id: str | None
    estado: str


class RenglonDetalleOut(BaseModel):
    """5.3 (spec "Product and Supplier Context Display"). `proveedores_catalogados`
    lee el catálogo real desde PR6 -- ver docstring de
    `services/pcp/renglones/service.py::listar_proveedores_disponibles_renglon`."""

    renglon: PcpRenglonOut
    producto: ProductoOut | None
    proveedores_catalogados: list[dict[str, Any]]


class SeleccionProveedores(BaseModel):
    """5.4 (spec "Supplier Selection for Negotiation"). Un único proveedor,
    varios, o "todos los disponibles" son todos, desde este servicio, la
    misma operación: una lista de `proveedor_id`. Quién arma esa lista
    (un solo id elegido a mano, o el resultado de "seleccionar todos") es
    responsabilidad del caller (router / futuro PR6), no de este modelo."""

    proveedor_ids: list[str]
