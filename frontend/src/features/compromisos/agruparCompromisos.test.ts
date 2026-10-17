import { describe, expect, it } from 'vitest'
import type { CompromisoEntrega } from '@/lib/api/compromisos'
import { agruparCompromisos, agruparEntregas, entregasPorFecha, filtrarEntregas } from './agruparCompromisos'

function fila(o: Partial<CompromisoEntrega> = {}): CompromisoEntrega {
  return {
    drogueria_id: 'd1',
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-1',
    version_numero: 1,
    exportado_at: '2026-10-01T10:00:00Z',
    cliente: 'Hospital Norte',
    cliente_codigo: null,
    cliente_codigos_legacy: [],
    entrega_oc_id: 'e-1',
    numero_entrega: 1,
    fecha_entrega_planificada: '2026-11-05',
    numero_renglon: 1,
    codigo_articulo: 'A1',
    descripcion: 'Ibuprofeno',
    cantidad_planificada: 10,
    situacion: 'futura',
    dias_atraso: 0,
    posicion_en_plan: 1,
    entregas_en_plan: 1,
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

describe('agruparEntregas', () => {
  it('junta renglones por entrega y conserva la posición dentro del plan', () => {
    const entregas = agruparEntregas([
      fila({ entrega_oc_id: 'e-2', numero_entrega: 3, fecha_entrega_planificada: '2026-10-23', posicion_en_plan: 2, entregas_en_plan: 3, numero_renglon: 2, cantidad_planificada: 5 }),
      fila({ entrega_oc_id: 'e-2', numero_entrega: 3, fecha_entrega_planificada: '2026-10-23', posicion_en_plan: 2, entregas_en_plan: 3, numero_renglon: 1, cantidad_planificada: 7 }),
      fila({ entrega_oc_id: 'e-1', numero_entrega: 1, fecha_entrega_planificada: '2026-10-20', posicion_en_plan: 1, entregas_en_plan: 3 }),
    ])

    expect(entregas.map((e) => e.entrega_oc_id)).toEqual(['e-1', 'e-2'])
    expect(entregas[1]).toMatchObject({ posicion_en_plan: 2, entregas_en_plan: 3 })
    expect(entregas[1].renglones.map((r) => r.numero_renglon)).toEqual([1, 2])
  })

  it('indexa las entregas por fecha', () => {
    const porFecha = entregasPorFecha(
      agruparEntregas([
        fila({ entrega_oc_id: 'a', fecha_entrega_planificada: '2026-10-23' }),
        fila({ entrega_oc_id: 'b', fecha_entrega_planificada: '2026-10-23', numero_oc: 'OC-2' }),
        fila({ entrega_oc_id: 'c', fecha_entrega_planificada: null }),
      ]),
    )

    expect(porFecha.get('2026-10-23')?.map((e) => e.entrega_oc_id)).toEqual(['a', 'b'])
    expect(porFecha.size).toBe(1)
  })

  it('filtra por cliente u OC sin distinguir mayúsculas ni acentos', () => {
    const entregas = agruparEntregas([
      fila({ entrega_oc_id: 'a', cliente: 'Clínica Olivos', numero_oc: '4471' }),
      fila({ entrega_oc_id: 'b', cliente: 'Htal. Alemán', numero_oc: '4520' }),
      fila({ entrega_oc_id: 'c', cliente: null, numero_oc: '4530' }),
    ])

    expect(filtrarEntregas(entregas, 'clinica').map((e) => e.entrega_oc_id)).toEqual(['a'])
    expect(filtrarEntregas(entregas, ' 452 ').map((e) => e.entrega_oc_id)).toEqual(['b'])
    expect(filtrarEntregas(entregas, '')).toHaveLength(3)
  })

  it('filtra por código interno o código de Progress del cliente', () => {
    const entregas = agruparEntregas([
      fila({ entrega_oc_id: 'a', cliente_codigo: 'CLI-0071', cliente_codigos_legacy: ['P1203'] }),
      fila({ entrega_oc_id: 'b', cliente_codigo: null, cliente_codigos_legacy: ['P5510', 'P5511'] }),
      fila({ entrega_oc_id: 'c', cliente: null, cliente_codigo: null, cliente_codigos_legacy: [] }),
    ])

    expect(filtrarEntregas(entregas, 'cli-0071').map((e) => e.entrega_oc_id)).toEqual(['a'])
    expect(filtrarEntregas(entregas, ' p5511 ').map((e) => e.entrega_oc_id)).toEqual(['b'])
    expect(filtrarEntregas(entregas, 'P12').map((e) => e.entrega_oc_id)).toEqual(['a'])
  })
})
