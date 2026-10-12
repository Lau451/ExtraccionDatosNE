import { describe, expect, it } from 'vitest'
import { fechaLegible } from './fechas'

describe('fechaLegible', () => {
  it('formatea un ISO con zona horaria igual que toLocaleString es-AR', () => {
    const iso = '2026-03-04T15:30:00Z'
    expect(fechaLegible(iso)).toBe(new Date(iso).toLocaleString('es-AR'))
  })

  it('formatea un ISO sin zona horaria', () => {
    const iso = '2026-03-04T15:30:00'
    expect(fechaLegible(iso)).toBe(new Date(iso).toLocaleString('es-AR'))
    expect(fechaLegible(iso)).toContain('2026')
  })

  it('devuelve el texto original si no es una fecha válida', () => {
    expect(fechaLegible('no-es-fecha')).toBe('no-es-fecha')
  })
})
