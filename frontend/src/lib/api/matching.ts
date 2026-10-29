import { presupuestacionFetch } from './presupuestacion'

/** Mirror of `services/presupuestacion/matching/models.py::EstadoMatching`. */
export type EstadoMatching = 'pendiente' | 'automatico' | 'sugerido' | 'confirmado' | 'sin_match'

/** Mirror of `matching/models.py::MetodoMatching`. */
export type MetodoMatching = 'exact' | 'fuzzy' | 'embedding' | 'manual'

/** Mirror of `matching/models.py::ProductoResumen`. */
export interface ProductoResumen {
  id: string
  nombre: string
  codigo_interno: string | null
}

/** Mirror of `matching/models.py::CandidatoRenglon`. Decimals travel as strings
 * with two decimals ("92.00"). */
export interface CandidatoRenglon {
  producto: ProductoResumen
  confianza: string
  metodo: MetodoMatching
  elegido: boolean
}

/** Mirror of `matching/models.py::RenglonMatching`. */
export interface RenglonMatching {
  item_proceso_id: string
  numero_renglon: number
  descripcion: string
  cantidad: string
  estado_matching: EstadoMatching
  confianza_matching: string | null
  producto: ProductoResumen | null
  candidatos: CandidatoRenglon[] // best first
}

/** Mirror of `matching/models.py::MatchingProceso`. */
export interface MatchingProceso {
  proceso_comercial_id: string
  nombre: string
  clase: string
  cliente: string | null
  renglones: RenglonMatching[] // by numero_renglon
}

/** Mirror of `matching/models.py::ProcesoConMatchingPendiente`. */
export interface ProcesoConMatchingPendiente {
  proceso_comercial_id: string
  proceso: string
  clase: string
  cliente: string | null
  pendientes: number
  sugeridos: number
}

export function obtenerMatchingProceso(procesoId: string): Promise<MatchingProceso> {
  return presupuestacionFetch<MatchingProceso>(`/procesos-comerciales/${procesoId}/matching`)
}

export function listarProcesosConMatchingPendiente(): Promise<ProcesoConMatchingPendiente[]> {
  return presupuestacionFetch<ProcesoConMatchingPendiente[]>('/matching/procesos')
}

/** Confirms `productoId` for the renglón (a candidato or any catalog producto)
 * and teaches the cliente's alias. Also re-chooses an already resolved renglón. */
export function confirmarMatching(itemProcesoId: string, productoId: string): Promise<unknown> {
  return presupuestacionFetch(`/items/${itemProcesoId}/confirmar-matching`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ producto_id: productoId }),
  })
}

/** Marks the renglón as having no producto in the catalog; invalidates the
 * alias that had matched it. */
export function marcarSinMatch(itemProcesoId: string): Promise<unknown> {
  return presupuestacionFetch(`/items/${itemProcesoId}/sin-match`, { method: 'POST' })
}
