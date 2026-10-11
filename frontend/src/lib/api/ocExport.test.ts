import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import { exportarAProgress } from './ocExport'

describe('cliente HTTP oc_export', () => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset())

  it('exportarAProgress hace POST al endpoint de la OC y devuelve la respuesta tal cual', async () => {
    const respuesta = {
      archivo: 'C001_OC-100_v1.csv',
      exportado_at: '2026-10-11T12:00:00Z',
      exportado_por: 'user-1',
      filas: 4,
    }
    vi.mocked(presupuestacionFetch).mockResolvedValue(respuesta)

    const resultado = await exportarAProgress('oc-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/exportar-progress', {
      method: 'POST',
    })
    expect(resultado).toEqual(respuesta)
  })

  it('propaga el error del cliente base (status y mensaje del backend) sin transformarlo', async () => {
    const error = Object.assign(new Error('No se puede exportar: falta CUIT; falta fecha'), { status: 422 })
    vi.mocked(presupuestacionFetch).mockRejectedValueOnce(error)

    const rechazo = await exportarAProgress('oc-1').catch((e: unknown) => e)

    expect(rechazo).toBe(error)
  })
})
