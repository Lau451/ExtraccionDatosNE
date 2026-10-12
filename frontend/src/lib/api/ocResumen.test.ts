import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import { obtenerOcResumen } from './ocResumen'

// Forma real por HTTP: los Decimal llegan como string.
const resumenCrudo = {
  orden_compra_id: 'oc-1',
  numero_oc: 'OC-100',
  cliente: { razon_social: 'Hospital Norte', cuit: '30123456789' },
  fecha_emision: '2026-10-01',
  fecha_entrega_estimada: null,
  direccion_entrega: null,
  notas: null,
  estado: 'confirmada',
  version_numero: 2,
  monto_total: null,
  exportacion: null,
  renglones: [
    {
      oc_item_id: 'item-1',
      numero_renglon: 1,
      numero_renglon_documento: '10',
      descripcion: 'Ibuprofeno 400mg',
      producto: { codigo_interno: 'P-1', nombre: 'Ibuprofeno' },
      cantidad: '100.00',
      precio_unitario: '12.50',
      monto_total: '1250.00',
      estado_vinculo: 'confirmado',
    },
    {
      oc_item_id: 'item-2',
      numero_renglon: 2,
      numero_renglon_documento: null,
      descripcion: 'Gasas',
      producto: null,
      cantidad: '5',
      precio_unitario: null,
      monto_total: null,
      estado_vinculo: 'pendiente',
    },
  ],
  entregas: [
    {
      numero_entrega: 1,
      fecha_entrega_planificada: '2026-11-05',
      estado: 'pendiente',
      items: [{ oc_item_id: 'item-1', cantidad_planificada: '40.50' }],
    },
  ],
}

describe('obtenerOcResumen', () => {
  beforeEach(() => {
    vi.mocked(presupuestacionFetch).mockReset()
  })

  it('pide GET /ordenes-compra/{id}/resumen', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(resumenCrudo)
    await obtenerOcResumen('oc-1')
    expect(presupuestacionFetch).toHaveBeenCalledWith('/ordenes-compra/oc-1/resumen')
  })

  it('parsea los Decimal-string a number y respeta los null', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(resumenCrudo)
    const resumen = await obtenerOcResumen('oc-1')

    expect(resumen.monto_total).toBeNull()
    expect(resumen.renglones[0].cantidad).toBe(100)
    expect(resumen.renglones[0].precio_unitario).toBe(12.5)
    expect(resumen.renglones[0].monto_total).toBe(1250)
    expect(resumen.renglones[1].precio_unitario).toBeNull()
    expect(resumen.renglones[1].monto_total).toBeNull()
    expect(resumen.entregas[0].items[0].cantidad_planificada).toBe(40.5)
    expect(resumen.cliente?.razon_social).toBe('Hospital Norte')
  })

  it('parsea el monto_total del encabezado cuando viene', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue({ ...resumenCrudo, monto_total: '1250.00' })
    expect((await obtenerOcResumen('oc-1')).monto_total).toBe(1250)
  })
})
