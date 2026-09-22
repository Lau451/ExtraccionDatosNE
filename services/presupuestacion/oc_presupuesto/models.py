# Modelos del módulo oc_presupuesto (design.md § Interfaces/Contracts, D12).
# Transcripción literal: todos los BaseModel se crean acá de una sola vez
# (tasks.md 2.7) porque Phase 2 (ranking) y Phase 3 (vinculación) comparten
# este único archivo -- no hay un models.py por fase.
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

EstadoVinculo = Literal["pendiente", "confirmado", "sin_presupuesto"]
OrigenVinculo = Literal["precio_exacto", "manual"]


class CandidatoPresupuesto(BaseModel):
    presupuesto_id: str
    proceso_comercial_id: str
    nombre_proceso: str
    # None cuando el presupuesto no vino del import legado (cargado a mano) o
    # cuando presupuesto_legacy_map no tiene fila para él (D2.1 / C1).
    numero_presupuesto: str | None
    estado: str
    generado_at: datetime
    cantidad_items: int
    # Puntaje del ranking (D2): cuántos renglones de ESTA OC coinciden exacto
    # en precio contra algún renglón de ESTE presupuesto.
    renglones_oc_con_coincidencia: int
    renglones_oc_totales: int


class PresupuestosCandidatosOut(BaseModel):
    orden_compra_id: str
    cliente_id: str
    razon_social_cliente: str
    # Total de presupuestos del cliente, coincidan o no. Permite distinguir
    # "no tiene presupuestos" de "tiene 12 y ninguno coincide" (D2).
    presupuestos_del_cliente: int
    candidatos: list[CandidatoPresupuesto]  # top 5, puntaje > 0, ya ordenados
    presupuesto_sugerido_id: str | None  # = candidatos[0] si hay; sugerido != elegido
    advertencias: list[str]


class RenglonPresupuesto(BaseModel):
    """Columna izquierda. Junta presupuesto_items + items_proceso (C5)."""

    presupuesto_item_id: str
    item_proceso_id: str
    numero_renglon: int
    descripcion: str
    cantidad_ofertada: Decimal | None
    precio_unitario: Decimal
    # COALESCE(presupuesto_items.producto_id, items_proceso.producto_id) -- lo
    # que se heredaría al confirmar. None es normal y no bloquea nada (D6).
    producto_id: str | None
    # Aviso N:1 (D5). Alcance: toda la droguería, no solo esta OC.
    renglones_oc_vinculados: int
    renglones_oc_vinculados_otras_oc: int
    cantidad_vinculada: Decimal


class CandidatoVinculo(BaseModel):
    presupuesto_item_id: str
    # fuzz.WRatio 0-100 sobre normalizar_descripcion(...). None cuando hay un
    # solo candidato: no hay nada que desempatar (D7). NUNCA filtra: ordena.
    similitud: Decimal | None


class RenglonOrdenCompra(BaseModel):
    """Columna derecha. `estado` se DERIVA, no está en la base (D4)."""

    oc_item_id: str
    numero_renglon: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    producto_id: str | None
    estado: EstadoVinculo
    presupuesto_item_id: str | None
    vinculo_origen: OrigenVinculo | None
    # Solo cuando estado == "pendiente". Vacío = ningún renglón del presupuesto
    # comparte el precio; el renglón queda pendiente y NO bloquea al resto.
    candidatos: list[CandidatoVinculo]


class MatchingOut(BaseModel):
    orden_compra_id: str
    numero_oc: str
    cliente_id: str
    # El presupuesto efectivamente usado, resuelto por el servidor cuando el
    # query param no vino (D8). None solo si el cliente no tiene ninguno.
    presupuesto_id: str | None
    renglones_presupuesto: list[RenglonPresupuesto]
    renglones_oc: list[RenglonOrdenCompra]
    advertencias: list[str]


class ConfirmarVinculoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    presupuesto_item_id: str
