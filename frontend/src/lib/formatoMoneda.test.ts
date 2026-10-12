import { describe, expect, it } from 'vitest'
import { formatearMoneda } from './formatoMoneda'

describe('formatearMoneda', () => {
  it('usa punto de miles, coma decimal y prefijo "$ "', () => {
    expect(formatearMoneda(1234.5)).toBe('$ 1.234,50')
    expect(formatearMoneda(1234567.89)).toBe('$ 1.234.567,89')
  })

  it('siempre muestra dos decimales', () => {
    expect(formatearMoneda(0)).toBe('$ 0,00')
    expect(formatearMoneda(5000)).toBe('$ 5.000,00')
  })

  it('redondea a dos decimales', () => {
    expect(formatearMoneda(12.346)).toBe('$ 12,35')
  })
})
