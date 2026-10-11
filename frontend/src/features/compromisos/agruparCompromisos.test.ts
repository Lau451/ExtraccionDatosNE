import { describe, expect, it } from 'vitest'
import type { CompromisoEntrega } from '@/lib/api/compromisos'
import { agruparCompromisos } from './agruparCompromisos'

function fila(o: Partial<CompromisoEntrega> = {}): CompromisoEntrega {
  return {
    drogueria_id: 'd1',
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-1',
    version_numero: 1,
    exportado_at: '2026-10-01T10:00:00Z',
    cliente: 'Hospital Norte',
    entrega_oc_id: 'e-1',
    numero_entrega: 1,
    fecha_entrega_planificada: '2026-11-05',
    numero_renglon: 1,
    codigo_articulo: 'A1',
    descripcion: 'Ibuprofeno',
    cantidad_planificada: 10,
    situacion: 'futura',
    dias_atraso: 0,
    ...o,
  }
}

describe('agruparCompromisos', () => {
  it('sin filas devuelve todo vacío', () => {
    expect(agruparCompromisos([])).toEqual({ vencidas: [], meses: [] })
  })

  it('separa las vencidas de las futuras', () => {
    const r = agruparCompromisos([
      fila({ entrega_oc_id: 'e-v', situacion: 'vencida', dias_atraso: 3, fecha_entrega_planificada: '2026-10-08' }),
      fila({ entrega_oc_id: 'e-f' }),
    ])
    expect(r.vencidas.map((e) => e.entrega_oc_id)).toEqual(['e-v'])
    expect(r.vencidas[0].dias_atraso).toBe(3)
    expect(r.meses.flatMap((m) => m.fechas.flatMap((f) => f.entregas)).map((e) => e.entrega_oc_id)).toEqual(['e-f'])
  })

  it('agrupa los renglones de una misma entrega', () => {
    const r = agruparCompromisos([
      fila({ numero_renglon: 1, descripcion: 'A', cantidad_planificada: 5 }),
      fila({ numero_renglon: 2, descripcion: 'B', cantidad_planificada: 7 }),
    ])
    const entregas = r.meses[0].fechas[0].entregas
    expect(entregas).toHaveLength(1)
    expect(entregas[0].numero_oc).toBe('OC-1')
    expect(entregas[0].cliente).toBe('Hospital Norte')
    expect(entregas[0].renglones.map((x) => [x.descripcion, x.cantidad_planificada])).toEqual([
      ['A', 5],
      ['B', 7],
    ])
  })

  it('agrupa por mes y por fecha, en orden cronológico', () => {
    const r = agruparCompromisos([
      fila({ entrega_oc_id: 'e-3', fecha_entrega_planificada: '2026-12-01' }),
      fila({ entrega_oc_id: 'e-2', fecha_entrega_planificada: '2026-11-20' }),
      fila({ entrega_oc_id: 'e-1', fecha_entrega_planificada: '2026-11-05' }),
      fila({ entrega_oc_id: 'e-1b', orden_compra_id: 'oc-2', numero_oc: 'OC-2', fecha_entrega_planificada: '2026-11-05' }),
    ])
    expect(r.meses.map((m) => m.clave)).toEqual(['2026-11', '2026-12'])
    expect(r.meses[0].fechas.map((f) => f.fecha)).toEqual(['2026-11-05', '2026-11-20'])
    expect(r.meses[0].fechas[0].entregas.map((e) => e.entrega_oc_id)).toEqual(['e-1', 'e-1b'])
  })

  it('ordena las vencidas por fecha y las entregas sin fecha van a un grupo final', () => {
    const r = agruparCompromisos([
      fila({ entrega_oc_id: 'v2', situacion: 'vencida', fecha_entrega_planificada: '2026-10-09' }),
      fila({ entrega_oc_id: 'v1', situacion: 'vencida', fecha_entrega_planificada: '2026-10-01' }),
      fila({ entrega_oc_id: 'sf', fecha_entrega_planificada: null }),
    ])
    expect(r.vencidas.map((e) => e.entrega_oc_id)).toEqual(['v1', 'v2'])
    expect(r.meses.at(-1)?.clave).toBe('sin-fecha')
  })
})
