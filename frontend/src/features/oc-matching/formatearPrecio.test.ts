import { describe, expect, it } from 'vitest'
import { formatearPrecio } from './formatearPrecio'

describe('formatearPrecio', () => {
  it('muestra siempre dos decimales, conservando el cero final', () => {
    expect(formatearPrecio(3093.7)).toBe('3093.70')
  })

  it('agrega los decimales a un precio entero', () => {
    expect(formatearPrecio(381)).toBe('381.00')
  })

  it('deja igual un precio que ya tiene dos decimales', () => {
    expect(formatearPrecio(363.77)).toBe('363.77')
  })
})
