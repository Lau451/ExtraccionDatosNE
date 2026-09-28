# Modelos del módulo oc_entregas (odd/tasks/oc-entregas-planificacion.md, T3).
# Mismo criterio que oc_presupuesto/models.py: todos los BaseModel en un único
# archivo, sin un models.py por endpoint.
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RenglonPlanificacion(BaseModel):
    """Un renglón CONFIRMADO de matching (D4 de orden-compra: solo esos entran
    a la planificación de entregas -- los pendientes bloquean, los
    descartados quedan afuera sin más)."""

    oc_item_id: str
    numero_renglon: int
    numero_renglon_documento: str | None = None
    descripcion: str
    cantidad: Decimal
    producto_id: str | None
    producto_nombre: str | None
    # None cuando `productos.presentacion` no matchea "Presentación x N"
    # (migración 0031) -- ese renglón simplemente no recibe advertencia de
    # divisibilidad, nunca bloquea.
    unidades_por_presentacion: int | None


class EntregaItemPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    oc_item_id: str
    cantidad: Decimal


class EntregaPlanIn(BaseModel):
    """Una entrega del plan que el usuario envía en el PUT. `numero_entrega`
    es 1-based y las N entregas del body deben cubrir exactamente 1..N sin
    huecos ni repetidos (422 si no)."""

    model_config = ConfigDict(extra="forbid")
    numero_entrega: int
    fecha_entrega_planificada: date | None = None
    items: list[EntregaItemPlanIn]


class PlanificarEntregasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entregas: list[EntregaPlanIn]


class EntregaItemPlanOut(BaseModel):
    oc_item_id: str
    cantidad_planificada: Decimal


class EntregaPlanOut(BaseModel):
    numero_entrega: int
    fecha_entrega_planificada: date | None
    estado: str
    items: list[EntregaItemPlanOut]


class PlanSugeridoRenglon(BaseModel):
    """Sugerencia de reparto para UN renglón confirmado, una cantidad por
    entrega (índice 0 == entrega 1). Ver service.sugerir_plan_renglon."""

    oc_item_id: str
    cantidades: list[Decimal]


class PlanificacionEntregasOut(BaseModel):
    orden_compra_id: str
    numero_oc: str
    # ordenes_compra.cantidad_entregas (T2) -- lo que declaró el documento
    # (o 1 por default). El usuario puede plantear un N distinto en el PUT.
    cantidad_entregas_sugerida: int
    renglones: list[RenglonPlanificacion]
    pendientes: int
    descartados: int
    puede_planificar: bool
    motivo: str | None
    plan_sugerido: list[PlanSugeridoRenglon]
    plan_actual: list[EntregaPlanOut]


class AdvertenciaDivisibilidad(BaseModel):
    oc_item_id: str
    numero_entrega: int
    cantidad: Decimal
    unidades_por_presentacion: int
    cantidad_sugerida: Decimal


class PlanificarEntregasOut(BaseModel):
    orden_compra_id: str
    entregas: list[EntregaPlanOut]
    # NUNCA bloquean (T3 acceptance criteria) -- el plan ya se creó cuando el
    # cliente ve advertencias.
    advertencias: list[AdvertenciaDivisibilidad]
