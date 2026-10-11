import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import { listarCompromisos } from './compromisos'

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
})
