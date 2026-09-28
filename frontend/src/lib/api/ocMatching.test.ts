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

// FastAPI/Pydantic v2 serializa `Decimal` como string en JSON. Este payload
// reproduce la forma real de la respuesta para fijar el parseo en el borde.
const matchingOutCrudo = {
  ...matchingOut,
  renglones_presupuesto: [
    {
      presupuesto_item_id: 'pi-1',
      item_proceso_id: 'ip-1',
      numero_renglon: 1,
      descripcion: 'CEFALEXINA',
      cantidad_ofertada: '100.00',
      precio_unitario: '3093.77',
      producto_id: null,
      renglones_oc_vinculados: 1,
      renglones_oc_vinculados_otras_oc: 0,
      cantidad_vinculada: '80.00',
    },
    {
      presupuesto_item_id: 'pi-2',
      item_proceso_id: 'ip-2',
      numero_renglon: 2,
      descripcion: 'BISACODILO',
      cantidad_ofertada: null,
      precio_unitario: '363.77',
      producto_id: null,
      renglones_oc_vinculados: 0,
      renglones_oc_vinculados_otras_oc: 0,
      cantidad_vinculada: '0',
    },
  ],
  renglones_oc: [
    {
      oc_item_id: 'oci-1',
      numero_renglon: 1,
      numero_renglon_documento: '7',
      descripcion: 'CEFALEXINA',
      cantidad: '50.00',
      precio_unitario: '3093.77',
      producto_id: null,
      estado: 'pendiente',
      presupuesto_item_id: null,
      vinculo_origen: null,
      candidatos: [
        { presupuesto_item_id: 'pi-1', similitud: '87.50' },
        { presupuesto_item_id: 'pi-2', similitud: null },
      ],
    },
  ],
}

describe.each([
  ['obtenerMatching', () => obtenerMatching('oc-1')],
  ['confirmarVinculo', () => confirmarVinculo('oc-1', 'oci-1', 'pi-1')],
  ['deshacerVinculo', () => deshacerVinculo('oc-1', 'oci-1')],
  ['descartarRenglon', () => descartarRenglon('oc-1', 'oci-1')],
])('%s parsea los Decimal que llegan como string', (_nombre, llamar) => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset().mockResolvedValue(matchingOutCrudo))

  it('convierte cantidades, precios y similitud a number y preserva los null', async () => {
    const matching = await llamar()

    const [conOferta, sinOferta] = matching.renglones_presupuesto
    expect(conOferta.cantidad_ofertada).toBe(100)
    expect(conOferta.precio_unitario).toBe(3093.77)
    expect(conOferta.cantidad_vinculada).toBe(80)
    expect(sinOferta.cantidad_ofertada).toBeNull()
    expect(sinOferta.cantidad_vinculada).toBe(0)

    const [renglonOc] = matching.renglones_oc
    expect(renglonOc.cantidad).toBe(50)
    expect(renglonOc.precio_unitario).toBe(3093.77)
    expect(renglonOc.candidatos.map((c) => c.similitud)).toEqual([87.5, null])
  })

  it('compara como número: 80 vinculado no supera 100 ofertado', async () => {
    const matching = await llamar()

    const [conOferta] = matching.renglones_presupuesto
    // Con strings, "80.00" > "100.00" es true (orden lexicográfico).
    expect(conOferta.cantidad_vinculada > (conOferta.cantidad_ofertada ?? 0)).toBe(false)
  })
})
