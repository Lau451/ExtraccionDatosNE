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
}

interface CompromisoEntregaCrudo extends Omit<CompromisoEntrega, 'cantidad_planificada'> {
  cantidad_planificada: string
}

/** GET /compromisos-entregas sin parámetros: todo lo vencido más los próximos
 * 6 meses (default del backend). Errores (`ApiError`): 403 rol sin permiso;
 * 422 usuario sin droguería (superadmin). */
export async function listarCompromisos(): Promise<CompromisoEntrega[]> {
  const crudas = await presupuestacionFetch<CompromisoEntregaCrudo[]>('/compromisos-entregas')
  return crudas.map((fila) => ({ ...fila, cantidad_planificada: Number(fila.cantidad_planificada) }))
}
