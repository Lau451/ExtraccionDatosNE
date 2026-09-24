import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import {
  confirmarVinculo,
  descartarRenglon,
  deshacerVinculo,
  obtenerMatching,
  obtenerPresupuestosCandidatos,
} from './ocMatching'

const matchingOut = {
  orden_compra_id: 'oc-1',
  numero_oc: '00104857',
  cliente_id: 'cli-1',
  presupuesto_id: 'pres-1',
  renglones_presupuesto: [],
  renglones_oc: [],
  advertencias: [],
}

describe('cliente HTTP oc_presupuesto', () => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset().mockResolvedValue(matchingOut))

  it('obtenerPresupuestosCandidatos llama a la ruta exacta del ranking (D2/D13)', async () => {
    await obtenerPresupuestosCandidatos('oc-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/presupuestos-candidatos')
  })

  it('obtenerMatching omite el query param cuando no se pasa presupuestoId (D8)', async () => {
    await obtenerMatching('oc-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/matching')
  })

  it('obtenerMatching serializa presupuesto_id cuando se pasa (D8)', async () => {
    await obtenerMatching('oc-1', 'pres-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/ordenes-compra/oc-1/matching?presupuesto_id=pres-1',
    )
  })

  it('confirmarVinculo hace POST con el body de ConfirmarVinculoRequest (D13)', async () => {
    await confirmarVinculo('oc-1', 'oci-1', 'pi-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/items/oci-1/vinculo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presupuesto_item_id: 'pi-1' }),
    })
  })

  it('deshacerVinculo hace DELETE sin body (D9)', async () => {
    await deshacerVinculo('oc-1', 'oci-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/items/oci-1/vinculo', {
      method: 'DELETE',
    })
  })

  it('descartarRenglon hace POST sin body (D4)', async () => {
    await descartarRenglon('oc-1', 'oci-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/ordenes-compra/oc-1/items/oci-1/descartar',
      { method: 'POST' },
    )
  })
})
