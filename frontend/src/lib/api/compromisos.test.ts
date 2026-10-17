import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import { listarCompromisos, obtenerProximaFecha } from './compromisos'

describe('cliente HTTP compromisos', () => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset())

  it('hace GET sin parámetros y convierte la cantidad (Decimal serializado como string) a número', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue([
      { numero_oc: 'OC-1', cantidad_planificada: '12.50', dias_atraso: 0, situacion: 'futura' },
    ])

    const filas = await listarCompromisos()

    expect(presupuestacionFetch).toHaveBeenCalledWith('/compromisos-entregas')
    expect(filas[0].cantidad_planificada).toBe(12.5)
    expect(filas[0].numero_oc).toBe('OC-1')
  })

  it('propaga el error del cliente base sin transformarlo', async () => {
    const error = Object.assign(new Error('sin droguería'), { status: 422 })
    vi.mocked(presupuestacionFetch).mockRejectedValueOnce(error)

    expect(await listarCompromisos().catch((e: unknown) => e)).toBe(error)
  })

  it('pasa el rango desde/hasta como query string', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue([])

    await listarCompromisos({ desde: '2026-09-28', hasta: '2026-11-08' })
    await listarCompromisos({ hasta: '2026-10-16' })

    expect(presupuestacionFetch).toHaveBeenNthCalledWith(1, '/compromisos-entregas?desde=2026-09-28&hasta=2026-11-08')
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(2, '/compromisos-entregas?hasta=2026-10-16')
  })

  it('obtiene la próxima fecha con compromisos después de una fecha', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValueOnce({ fecha: '2026-11-02' }).mockResolvedValueOnce({ fecha: null })

    expect(await obtenerProximaFecha('2026-10-31')).toBe('2026-11-02')
    expect(await obtenerProximaFecha('2027-12-31')).toBeNull()
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(1, '/compromisos-entregas/proxima-fecha?despues_de=2026-10-31')
  })
})
