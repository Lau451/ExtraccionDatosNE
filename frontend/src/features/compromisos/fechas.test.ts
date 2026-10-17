import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  diasDeSemana,
  diaSemanaLargo,
  etiquetaMes,
  etiquetaSemana,
  fechaCorta,
  fechaDiaMes,
  hoyBuenosAires,
  inicioSemana,
  mesDe,
  nombreMes,
  semanasDelMes,
  sumarDias,
  sumarMeses,
} from './fechas'

describe('fechas de calendario', () => {
  afterEach(() => vi.useRealTimers())

  it('hoy es la fecha de Buenos Aires, no la UTC', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-18T02:30:00Z'))
    expect(hoyBuenosAires()).toBe('2026-10-17')
  })

  it('suma días cruzando meses y años', () => {
    expect(sumarDias('2026-10-31', 1)).toBe('2026-11-01')
    expect(sumarDias('2026-03-01', -1)).toBe('2026-02-28')
    expect(sumarDias('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('la semana empieza el lunes', () => {
    expect(inicioSemana('2026-10-17')).toBe('2026-10-12')
    expect(inicioSemana('2026-10-12')).toBe('2026-10-12')
    expect(inicioSemana('2026-10-18')).toBe('2026-10-12')
    expect(diasDeSemana('2026-10-19')).toEqual([
      '2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25',
    ])
  })

  it('arma las semanas completas que cubren el mes (4 a 6)', () => {
    const octubre = semanasDelMes('2026-10')
    expect(octubre).toHaveLength(5)
    expect(octubre[0][0]).toBe('2026-09-28')
    expect(octubre[4][6]).toBe('2026-11-01')
    expect(semanasDelMes('2026-08')).toHaveLength(6)
    expect(semanasDelMes('2027-02')).toHaveLength(4)
  })

  it('navega meses', () => {
    expect(mesDe('2026-10-17')).toBe('2026-10')
    expect(sumarMeses('2026-12', 1)).toBe('2027-01')
    expect(sumarMeses('2026-01', -1)).toBe('2025-12')
  })

  it('formatea etiquetas en castellano', () => {
    expect(etiquetaMes('2026-10')).toBe('Octubre 2026')
    expect(nombreMes('2026-11')).toBe('noviembre')
    expect(etiquetaSemana('2026-10-19')).toBe('19 – 25 de octubre 2026')
    expect(etiquetaSemana('2026-09-28')).toBe('28 sep – 4 oct 2026')
    expect(etiquetaSemana('2026-12-28')).toBe('28 dic 2026 – 3 ene 2027')
    expect(diaSemanaLargo('2026-10-23')).toBe('viernes')
    expect(fechaDiaMes('2026-10-23')).toBe('23 de octubre')
    expect(fechaCorta('2026-09-29')).toBe('29/09')
  })
})
