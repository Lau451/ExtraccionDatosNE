import { presupuestacionFetch } from './presupuestacion'

/** Espejo de `compromisos/models.py::CompromisoEntrega`: un renglón de una
 * entrega abierta de una OC exportada a Progress (vista `v_compromisos_entregas`).
 * `cantidad_planificada` es Decimal en el backend (viaja como string) y acá ya
 * está convertida a número. */
export interface CompromisoEntrega {
  drogueria_id: string
  orden_compra_id: string
  numero_oc: string
  version_numero: number | null
  exportado_at: string
  cliente: string | null
  entrega_oc_id: string
  numero_entrega: number
  // 'YYYY-MM-DD'
  fecha_entrega_planificada: string | null
  numero_renglon: number | null
  codigo_articulo: string | null
  descripcion: string | null
  cantidad_planificada: number
  situacion: 'vencida' | 'futura'
  dias_atraso: number
  // Lugar de la entrega entre las entregas del plan de la OC y cuántas son ("Entrega 2 de 3").
  posicion_en_plan: number
  entregas_en_plan: number
}

interface CompromisoEntregaCrudo extends Omit<CompromisoEntrega, 'cantidad_planificada'> {
  cantidad_planificada: string
}

/** GET /compromisos-entregas. Sin parámetros: todo lo vencido más los próximos
 * 6 meses (default del backend). Con `desde`: solo [desde, hasta]; con solo
 * `hasta`: todo lo anterior o igual a `hasta` (p. ej. las vencidas con
 * hasta = ayer). Fechas 'YYYY-MM-DD'. Errores (`ApiError`): 403 rol sin permiso;
 * 422 usuario sin droguería (superadmin) o rango inválido. */
export async function listarCompromisos(rango: { desde?: string; hasta?: string } = {}): Promise<CompromisoEntrega[]> {
  const parametros = new URLSearchParams()
  if (rango.desde) parametros.set('desde', rango.desde)
  if (rango.hasta) parametros.set('hasta', rango.hasta)
  const query = parametros.toString()
  const crudas = await presupuestacionFetch<CompromisoEntregaCrudo[]>(
    query ? `/compromisos-entregas?${query}` : '/compromisos-entregas',
  )
  return crudas.map((fila) => ({ ...fila, cantidad_planificada: Number(fila.cantidad_planificada) }))
}

/** GET /compromisos-entregas/proxima-fecha: primera fecha con compromisos
 * estrictamente posterior a `despuesDe` ('YYYY-MM-DD'), o null si no hay. */
export async function obtenerProximaFecha(despuesDe: string): Promise<string | null> {
  const { fecha } = await presupuestacionFetch<{ fecha: string | null }>(
    `/compromisos-entregas/proxima-fecha?despues_de=${despuesDe}`,
  )
  return fecha
}
