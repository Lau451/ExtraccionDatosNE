import type { CompromisoEntrega } from '@/lib/api/compromisos'

export interface RenglonCompromiso {
  numero_renglon: number | null
  codigo_articulo: string | null
  descripcion: string | null
  cantidad_planificada: number
}

export interface EntregaCompromiso {
  entrega_oc_id: string
  orden_compra_id: string
  numero_oc: string
  numero_entrega: number
  cliente: string | null
  fecha_entrega_planificada: string | null
  situacion: CompromisoEntrega['situacion']
  dias_atraso: number
  renglones: RenglonCompromiso[]
}

export interface FechaCompromisos {
  fecha: string | null
  entregas: EntregaCompromiso[]
}

export interface MesCompromisos {
  /** 'YYYY-MM' o 'sin-fecha' */
  clave: string
  fechas: FechaCompromisos[]
}

export interface AgendaCompromisos {
  vencidas: EntregaCompromiso[]
  meses: MesCompromisos[]
}

const SIN_FECHA = 'sin-fecha'

function porEntrega(a: EntregaCompromiso, b: EntregaCompromiso): number {
  return (
    (a.fecha_entrega_planificada ?? '').localeCompare(b.fecha_entrega_planificada ?? '') ||
    a.numero_oc.localeCompare(b.numero_oc) ||
    a.numero_entrega - b.numero_entrega
  )
}

/** Agrupa las filas (una por renglón) en entregas y arma la agenda: vencidas
 * aparte y el resto por mes y por fecha, en orden cronológico. Las entregas
 * sin fecha van a un grupo final. Función pura: no depende del orden de entrada. */
export function agruparCompromisos(filas: CompromisoEntrega[]): AgendaCompromisos {
  const entregas = new Map<string, EntregaCompromiso>()
  for (const fila of filas) {
    let entrega = entregas.get(fila.entrega_oc_id)
    if (!entrega) {
      entrega = {
        entrega_oc_id: fila.entrega_oc_id,
        orden_compra_id: fila.orden_compra_id,
        numero_oc: fila.numero_oc,
        numero_entrega: fila.numero_entrega,
        cliente: fila.cliente,
        fecha_entrega_planificada: fila.fecha_entrega_planificada,
        situacion: fila.situacion,
        dias_atraso: fila.dias_atraso,
        renglones: [],
      }
      entregas.set(fila.entrega_oc_id, entrega)
    }
    entrega.renglones.push({
      numero_renglon: fila.numero_renglon,
      codigo_articulo: fila.codigo_articulo,
      descripcion: fila.descripcion,
      cantidad_planificada: fila.cantidad_planificada,
    })
  }

  const ordenadas = [...entregas.values()].sort(porEntrega)
  for (const entrega of ordenadas) {
    entrega.renglones.sort((a, b) => (a.numero_renglon ?? 0) - (b.numero_renglon ?? 0))
  }

  const meses = new Map<string, Map<string | null, EntregaCompromiso[]>>()
  for (const entrega of ordenadas.filter((e) => e.situacion !== 'vencida')) {
    const fecha = entrega.fecha_entrega_planificada
    const clave = fecha ? fecha.slice(0, 7) : SIN_FECHA
    const fechas = meses.get(clave) ?? new Map<string, EntregaCompromiso[]>()
    fechas.set(fecha, [...(fechas.get(fecha) ?? []), entrega])
    meses.set(clave, fechas)
  }

  return {
    vencidas: ordenadas.filter((e) => e.situacion === 'vencida'),
    meses: [...meses.entries()]
      .sort(([a], [b]) => (a === SIN_FECHA ? 1 : b === SIN_FECHA ? -1 : a.localeCompare(b)))
      .map(([clave, fechas]) => ({
        clave,
        fechas: [...fechas.entries()].map(([fecha, entregasDeFecha]) => ({ fecha, entregas: entregasDeFecha })),
      })),
  }
}
