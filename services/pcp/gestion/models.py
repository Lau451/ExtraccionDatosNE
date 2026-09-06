from typing import Literal

from pydantic import BaseModel

# D2/D11 (openspec/changes/gestor-pcp/design.md) -- secuencia fija del `pcp`
# (0011_pcp_modelo.sql M1 ck_pcp_estado) y discriminador `origen` de cómo se
# originó el PCP en sí (no confundir con pcp_renglones.origen, por renglón).
EstadoPcp = Literal["nueva", "en_gestion", "esperando_respuesta", "cerrada"]
OrigenPcp = Literal["manual", "regla", "import_legado"]


class PcpCreate(BaseModel):
    """Alta de un PCP (spec pcp-gestion, "PCP Creation from Presupuesto").

    `proceso_comercial_id`/`drogueria_id` no se piden acá: el servicio los
    deriva del `presupuesto_id` (lectura directa de `presupuestos`, nunca vía
    `services.presupuestacion.presupuestos.repository` -- D1 prohíbe importar
    el repository de otro módulo, no leer su tabla), así un valor de cliente
    nunca puede desincronizar el PCP de su presupuesto origen.
    """

    presupuesto_id: str
    fecha_entrega_solicitada: str | None = None
    solicitante_id: str | None = None
    sector_id: str | None = None
    origen: OrigenPcp | None = None
    notas: str | None = None


class PcpTransicionEstado(BaseModel):
    estado: EstadoPcp


class PcpOut(BaseModel):
    id: str
    drogueria_id: str
    presupuesto_id: str
    proceso_comercial_id: str
    estado: str
    fecha_entrega_solicitada: str | None
    solicitante_id: str | None
    sector_id: str | None
    origen: str | None
    regla_pcp_id: str | None
    notas: str | None
    cerrada_at: str | None
    cerrada_por: str | None
