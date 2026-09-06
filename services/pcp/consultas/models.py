from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

# D9 (openspec/changes/gestor-pcp/design.md) -- discriminador de
# `pcp_consultas.estado` (0012_pcp_extras.sql M4 ck_pcpc_estado). `enviada`
# nunca se escribe desde este PR -- llega recién con el adaptador de envío
# (PR11, tasks.md Fase 11).
EstadoConsulta = Literal["borrador", "enviada", "respondida", "cancelada"]


class SeleccionParaAgrupar(BaseModel):
    """Identifica una fila `pcp_renglon_resultados` (D4, 0011_pcp_modelo.sql
    M4) ya creada por `services/pcp/renglones/service.py::seleccionar_proveedores`
    (PR5): el renglón y el proveedor con el que fue seleccionado a negociar.
    Esa fila -- no una columna nueva en `pcp_renglones` -- es la única prueba
    en todo el esquema de que "un renglón está asignado a un proveedor P"
    (spec `pcp-consultas-agrupadas`, "Cross-PCP Grouping by Supplier");
    `services/pcp/consultas/service.py::agrupar_renglones` la exige antes de
    agrupar (`negociacion_service.obtener_resultado` levanta `NotFoundError`
    si no existe).

    `cantidad_consultada` es opcional: si no se especifica,
    `pcp_consulta_renglones.cantidad_consultada` queda NULL y el PDF usa la
    cantidad snapshot del renglón (`pcp_renglones.cantidad`, D2).
    """

    pcp_renglon_id: str
    proveedor_id: str
    cantidad_consultada: Decimal | None = None


class AgruparConsultaCreate(BaseModel):
    """Alta/agrupamiento de una o más consultas (spec
    `pcp-consultas-agrupadas`, "Cross-PCP Grouping by Supplier").

    Decisión de diseño (tasks.md 9.3-9.4, dejada explícitamente a este run
    por el launch prompt): un único `POST` puede traer selecciones de más de
    un proveedor a la vez. El servicio nunca elige un proveedor y descarta
    el resto -- `pcp_consultas.proveedor_id` es una única columna NOT NULL
    (0012_pcp_extras.sql M4), así que "una consulta por proveedor" es una
    invariante de esquema, no una elección de UX. En vez de rechazar la
    request, `agrupar_renglones` agrupa las selecciones por `proveedor_id`
    internamente y crea una consulta por cada proveedor distinto presente,
    devolviendo la lista completa (ver docstring de
    `services/pcp/consultas/service.py`).
    """

    selecciones: list[SeleccionParaAgrupar]
    contacto_id: str | None = None
    # Mismo criterio de tipado que PcpCreate.fecha_entrega_solicitada
    # (services/pcp/gestion/models.py): fecha como `str | None`, no `date`,
    # para pasar directo a Supabase sin una conversión intermedia.
    fecha_respuesta_esperada: str | None = None
    canal: str | None = None


class ConsultaOut(BaseModel):
    id: str
    drogueria_id: str
    proveedor_id: str
    contacto_id: str | None
    estado: str
    canal: str | None
    fecha_envio: str | None
    fecha_respuesta_esperada: str | None
    documento_path: str | None


class ConsultaRenglonOut(BaseModel):
    id: str
    drogueria_id: str
    consulta_id: str
    pcp_renglon_id: str
    cantidad_consultada: Decimal | None
