import { describe, expect, it } from 'vitest'
import { ESTADO_META, ESTADOS_DERIVADOS, estadoDerivadoDe, estadoGrupoDe } from './estadoExtraccion'

describe('estadoDerivadoDe (T2, validar-extraccion-organizacion)', () => {
  it('validado=true manda "validada" sin importar el status subyacente', () => {
    expect(estadoDerivadoDe({ status: 'completed', validado: true })).toBe('validada')
    expect(estadoDerivadoDe({ status: 'partial', validado: true })).toBe('validada')
  })

  it('status="processing" y sin validar -> "procesando"', () => {
    expect(estadoDerivadoDe({ status: 'processing', validado: false })).toBe('procesando')
  })

  it('status="completed" y sin validar -> "procesado"', () => {
    expect(estadoDerivadoDe({ status: 'completed', validado: false })).toBe('procesado')
  })

  it('status="partial" y sin validar -> "procesado_advertencias"', () => {
    expect(estadoDerivadoDe({ status: 'partial', validado: false })).toBe('procesado_advertencias')
  })

  it('status="failed" -> "error" (validado siempre es false para failed, pero no se asume)', () => {
    expect(estadoDerivadoDe({ status: 'failed', validado: false })).toBe('error')
  })

  it('un status desconocido/inesperado cae de forma defensiva en "error", no en un estado "sano"', () => {
    expect(estadoDerivadoDe({ status: 'algo-nuevo' as never, validado: false })).toBe('error')
  })
})

describe('ESTADO_META', () => {
  it('define label y badgeClass para cada uno de los 5 estados derivados', () => {
    for (const estado of ESTADOS_DERIVADOS) {
      expect(ESTADO_META[estado].label).toBeTruthy()
      expect(ESTADO_META[estado].badgeClass).toBeTruthy()
    }
  })

  it('las etiquetas coinciden con la decisión del usuario (2026-09-26)', () => {
    expect(ESTADO_META.procesando.label).toBe('Procesando')
    expect(ESTADO_META.procesado.label).toBe('Procesado')
    expect(ESTADO_META.procesado_advertencias.label).toBe('Procesado con advertencias')
    expect(ESTADO_META.error.label).toBe('Error')
    expect(ESTADO_META.validada.label).toBe('Validada')
  })
})

describe('estadoGrupoDe (T3, validar-extraccion-organizacion) -- estado agregado del encabezado de grupo', () => {
  it('si todos los miembros comparten el mismo estado derivado, ese es el estado del grupo', () => {
    expect(estadoGrupoDe(['procesado', 'procesado'])).toBe('procesado')
    expect(estadoGrupoDe(['validada', 'validada', 'validada'])).toBe('validada')
  })

  it('con estados mixtos, gana el "menos avanzado" según el orden definido en T3', () => {
    // procesando < error < procesado_advertencias < procesado < validada
    expect(estadoGrupoDe(['procesando', 'validada'])).toBe('procesando')
    expect(estadoGrupoDe(['error', 'procesado'])).toBe('error')
    expect(estadoGrupoDe(['procesado_advertencias', 'procesado'])).toBe('procesado_advertencias')
    expect(estadoGrupoDe(['procesado', 'validada'])).toBe('procesado')
  })

  it('el orden es transitivo con 3+ miembros de estados distintos', () => {
    expect(estadoGrupoDe(['validada', 'procesado', 'error', 'procesando'])).toBe('procesando')
    expect(estadoGrupoDe(['validada', 'procesado', 'procesado_advertencias'])).toBe('procesado_advertencias')
  })

  it('sin miembros devuelve null en vez de lanzar (F5, revisión de T3)', () => {
    expect(estadoGrupoDe([])).toBeNull()
  })
})
