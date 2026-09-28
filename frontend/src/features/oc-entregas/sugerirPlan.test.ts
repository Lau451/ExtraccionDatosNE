import { describe, expect, it } from 'vitest'
import { sugerirCantidadDivisible, sugerirPlanRenglon } from './sugerirPlan'

describe('sugerirPlanRenglon (espejo de oc_entregas/service.py::sugerir_plan_renglon, T3)', () => {
  it('100 unidades, presentación x25, 3 entregas -> 50/25/25 (design.md D8 + T3)', () => {
    expect(sugerirPlanRenglon(100, 25, 3)).toEqual([50, 25, 25])
  })

  it('110 unidades, presentación x25, 3 entregas -> el resto va a la última (50/25/35)', () => {
    expect(sugerirPlanRenglon(110, 25, 3)).toEqual([50, 25, 35])
  })

  it('sin presentación conocida (null) reparte parejo con repartir_cantidad', () => {
    expect(sugerirPlanRenglon(10, null, 3)).toEqual([4, 3, 3])
  })

  it('presentación undefined se trata igual que null', () => {
    expect(sugerirPlanRenglon(10, undefined, 3)).toEqual([4, 3, 3])
  })

  it('presentación <= 0 se trata como desconocida, nunca divide por cero', () => {
    expect(sugerirPlanRenglon(10, 0, 3)).toEqual([4, 3, 3])
  })

  it('1 sola entrega devuelve toda la cantidad', () => {
    expect(sugerirPlanRenglon(100, 25, 1)).toEqual([100])
  })

  it('menos de 1 entrega devuelve un arreglo vacío', () => {
    expect(sugerirPlanRenglon(100, 25, 0)).toEqual([])
  })

  it('invariante: la suma siempre da la cantidad total, con o sin presentación', () => {
    const casos: Array<[number, number | null, number]> = [
      [100, 25, 3],
      [110, 25, 3],
      [37, 10, 4],
      [10, null, 3],
      [7, 4, 5],
    ]
    for (const [cantidad, u, entregas] of casos) {
      const resultado = sugerirPlanRenglon(cantidad, u, entregas)
      expect(resultado.reduce((acumulado, valor) => acumulado + valor, 0)).toBe(cantidad)
    }
  })
})

describe('sugerirCantidadDivisible (espejo de _advertencias_divisibilidad, T3)', () => {
  it('sugiere el múltiplo inferior más cercano', () => {
    expect(sugerirCantidadDivisible(30, 25)).toBe(25)
  })

  it('cuando el múltiplo inferior da cero, sugiere la presentación completa', () => {
    expect(sugerirCantidadDivisible(10, 25)).toBe(25)
  })

  it('una cantidad ya múltiplo se sugiere igual a sí misma', () => {
    expect(sugerirCantidadDivisible(50, 25)).toBe(50)
  })
})
