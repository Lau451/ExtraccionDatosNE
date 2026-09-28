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

/** GET /ordenes-compra/{id}/entregas/planificacion (T3): contexto completo de
 * la pantalla de planificación. No escribe nada. */
export function obtenerPlanificacionEntregas(ordenCompraId: string): Promise<PlanificacionEntregasOut> {
  return presupuestacionFetch<PlanificacionEntregasOut>(
    `/ordenes-compra/${ordenCompraId}/entregas/planificacion`,
  )
}

/** PUT /ordenes-compra/{id}/entregas/planificacion (T3): crea o reemplaza el
 * plan de entregas. 409 cuando hay renglones pendientes o el plan está
 * bloqueado (una entrega dejó de estar `pendiente`); 422 en validaciones de
 * forma (numeración, renglón ajeno/no confirmado, suma por renglón, más de
 * 24 entregas). */
export function planificarEntregas(
  ordenCompraId: string,
  entregas: EntregaPlanIn[],
): Promise<PlanificarEntregasOut> {
  return presupuestacionFetch<PlanificarEntregasOut>(
    `/ordenes-compra/${ordenCompraId}/entregas/planificacion`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entregas }),
    },
  )
}
