import { presupuestacionFetch } from './presupuestacion'

/** Espejo literal de `oc_entregas/models.py::RenglonPlanificacion` (T3): un
 * renglón CONFIRMADO de matching -- solo esos entran a la planificación de
 * entregas. */
export interface RenglonPlanificacion {
  oc_item_id: string
  numero_renglon: number
  numero_renglon_documento: string | null
  descripcion: string
  cantidad: number
  producto_id: string | null
  producto_nombre: string | null
  // null cuando `productos.presentacion` no matchea "Presentación x N"
  // (migración 0031) -- ese renglón no recibe advertencia de divisibilidad,
  // nunca bloquea.
  unidades_por_presentacion: number | null
}

/** Espejo literal de `oc_entregas/models.py::EntregaItemPlanIn` (T3). */
export interface EntregaItemPlanIn {
  oc_item_id: string
  cantidad: number
}

/** Espejo literal de `oc_entregas/models.py::EntregaPlanIn` (T3):
 * `numero_entrega` es 1-based, las N entregas del body deben cubrir
 * exactamente 1..N sin huecos ni repetidos. */
export interface EntregaPlanIn {
  numero_entrega: number
  fecha_entrega_planificada: string | null
  items: EntregaItemPlanIn[]
}

/** Espejo literal de `oc_entregas/models.py::EntregaItemPlanOut` (T3). */
export interface EntregaItemPlanOut {
  oc_item_id: string
  cantidad_planificada: number
}

/** Espejo literal de `oc_entregas/models.py::EntregaPlanOut` (T3). */
export interface EntregaPlanOut {
  numero_entrega: number
  fecha_entrega_planificada: string | null
  estado: string
  items: EntregaItemPlanOut[]
}

/** Espejo literal de `oc_entregas/models.py::PlanSugeridoRenglon` (T3): una
 * cantidad por entrega (índice 0 == entrega 1) para UN renglón confirmado. */
export interface PlanSugeridoRenglon {
  oc_item_id: string
  cantidades: number[]
}

/** Espejo literal de `oc_entregas/models.py::PlanificacionEntregasOut` (T3). */
export interface PlanificacionEntregasOut {
  orden_compra_id: string
  numero_oc: string
  cantidad_entregas_sugerida: number
  renglones: RenglonPlanificacion[]
  pendientes: number
  descartados: number
  puede_planificar: boolean
  motivo: string | null
  plan_sugerido: PlanSugeridoRenglon[]
  plan_actual: EntregaPlanOut[]
}

/** Espejo literal de `oc_entregas/models.py::AdvertenciaDivisibilidad` (T3).
 * NUNCA bloquea (T3 acceptance criteria): el plan ya se creó cuando el
 * cliente ve advertencias. */
export interface AdvertenciaDivisibilidad {
  oc_item_id: string
  numero_entrega: number
  cantidad: number
  unidades_por_presentacion: number
  cantidad_sugerida: number
}

/** Espejo literal de `oc_entregas/models.py::PlanificarEntregasOut` (T3). */
export interface PlanificarEntregasOut {
  orden_compra_id: string
  entregas: EntregaPlanOut[]
  advertencias: AdvertenciaDivisibilidad[]
}

// -- Fix de review: formato real por HTTP -----------------------------------
//
// FastAPI/Pydantic v2 serializa `Decimal` como STRING en JSON, nunca como
// number (confirmado con un TestClient en tests/oc_entregas/test_router.py,
// caso `test_get_planificacion_devuelve_renglones_confirmados_y_plan_sugerido`).
// Los campos `cantidad`, `cantidad_planificada`, `cantidades` y
// `cantidad_sugerida` de `oc_entregas/models.py` son todos `Decimal`. Los
// tipos de arriba son la forma ya PARSEADA que usa el resto del frontend;
// estos `*Crudo` son la forma real de la respuesta, usados solo acá adentro
// para convertir en el borde del API client -- sin esto, sumar cantidades en
// el componente concatena strings ("50" + "25" -> "5025") en vez de sumar, y
// el botón Guardar nunca se habilita.
//
// `ocMatching.ts` sigue la misma convención (parsea en el borde).

interface RenglonPlanificacionCrudo extends Omit<RenglonPlanificacion, 'cantidad'> {
  cantidad: string
}

interface EntregaItemPlanOutCrudo {
  oc_item_id: string
  cantidad_planificada: string
}

interface EntregaPlanOutCrudo extends Omit<EntregaPlanOut, 'items'> {
  items: EntregaItemPlanOutCrudo[]
}

interface PlanSugeridoRenglonCrudo {
  oc_item_id: string
  cantidades: string[]
}

interface PlanificacionEntregasOutCrudo
  extends Omit<PlanificacionEntregasOut, 'renglones' | 'plan_sugerido' | 'plan_actual'> {
  renglones: RenglonPlanificacionCrudo[]
  plan_sugerido: PlanSugeridoRenglonCrudo[]
  plan_actual: EntregaPlanOutCrudo[]
}

interface AdvertenciaDivisibilidadCrudo extends Omit<AdvertenciaDivisibilidad, 'cantidad' | 'cantidad_sugerida'> {
  cantidad: string
  cantidad_sugerida: string
}

interface PlanificarEntregasOutCrudo extends Omit<PlanificarEntregasOut, 'entregas' | 'advertencias'> {
  entregas: EntregaPlanOutCrudo[]
  advertencias: AdvertenciaDivisibilidadCrudo[]
}

function parsearEntregaPlanOut(cruda: EntregaPlanOutCrudo): EntregaPlanOut {
  return {
    ...cruda,
    items: cruda.items.map((item) => ({
      oc_item_id: item.oc_item_id,
      cantidad_planificada: Number(item.cantidad_planificada),
    })),
  }
}

function parsearPlanificacion(cruda: PlanificacionEntregasOutCrudo): PlanificacionEntregasOut {
  return {
    ...cruda,
    renglones: cruda.renglones.map((renglon) => ({ ...renglon, cantidad: Number(renglon.cantidad) })),
    plan_sugerido: cruda.plan_sugerido.map((plan) => ({
      oc_item_id: plan.oc_item_id,
      cantidades: plan.cantidades.map(Number),
    })),
    plan_actual: cruda.plan_actual.map(parsearEntregaPlanOut),
  }
}

function parsearPlanificarEntregasOut(cruda: PlanificarEntregasOutCrudo): PlanificarEntregasOut {
  return {
    ...cruda,
    entregas: cruda.entregas.map(parsearEntregaPlanOut),
    advertencias: cruda.advertencias.map((advertencia) => ({
      ...advertencia,
      cantidad: Number(advertencia.cantidad),
      cantidad_sugerida: Number(advertencia.cantidad_sugerida),
    })),
  }
}

// Fix de review: NUMERIC(12,2) en la base -- redondear a centavos antes de
// enviar evita que un residuo binario de la aritmética del cliente (p.ej.
// `0.1 + 0.2 === 0.30000000000000004`) viaje tal cual en el body del PUT.
function redondearACentavos(cantidad: number): number {
  return Math.round(cantidad * 100) / 100
}

/** GET /ordenes-compra/{id}/entregas/planificacion (T3): contexto completo de
 * la pantalla de planificación. No escribe nada. */
export async function obtenerPlanificacionEntregas(ordenCompraId: string): Promise<PlanificacionEntregasOut> {
  const cruda = await presupuestacionFetch<PlanificacionEntregasOutCrudo>(
    `/ordenes-compra/${ordenCompraId}/entregas/planificacion`,
  )
  return parsearPlanificacion(cruda)
}

/** PUT /ordenes-compra/{id}/entregas/planificacion (T3): crea o reemplaza el
 * plan de entregas. 409 cuando hay renglones pendientes o el plan está
 * bloqueado (una entrega dejó de estar `pendiente`); 422 en validaciones de
 * forma (numeración, renglón ajeno/no confirmado, suma por renglón, más de
 * 24 entregas). */
export async function planificarEntregas(
  ordenCompraId: string,
  entregas: EntregaPlanIn[],
): Promise<PlanificarEntregasOut> {
  const entregasRedondeadas = entregas.map((entrega) => ({
    ...entrega,
    items: entrega.items.map((item) => ({ ...item, cantidad: redondearACentavos(item.cantidad) })),
  }))
  const cruda = await presupuestacionFetch<PlanificarEntregasOutCrudo>(
    `/ordenes-compra/${ordenCompraId}/entregas/planificacion`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entregas: entregasRedondeadas }),
    },
  )
  return parsearPlanificarEntregasOut(cruda)
}
