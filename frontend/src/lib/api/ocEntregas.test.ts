import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn() }))

import { presupuestacionFetch } from './presupuestacion'
import { obtenerPlanificacionEntregas, planificarEntregas } from './ocEntregas'

/** Forma real de la respuesta (fix de review, verificado con TestClient en
 * tests/oc_entregas/test_router.py): FastAPI/Pydantic v2 serializa `Decimal`
 * como STRING, nunca como number. Estos fixtures usan ese formato real -- no
 * el shape ya parseado -- para que un parseo faltante haga fallar el test. */
const planificacionCruda = {
  orden_compra_id: 'oc-1',
  numero_oc: 'OC-100',
  cantidad_entregas_sugerida: 3,
  renglones: [
    {
      oc_item_id: 'item-1',
      numero_renglon: 1,
      numero_renglon_documento: null,
      descripcion: 'Ibuprofeno 400mg',
      cantidad: '100.00',
      producto_id: 'prod-1',
      producto_nombre: 'Ibuprofeno 400mg',
      unidades_por_presentacion: 25,
    },
  ],
  pendientes: 0,
  descartados: 0,
  puede_planificar: true,
  motivo: null,
  plan_sugerido: [{ oc_item_id: 'item-1', cantidades: ['50', '25', '25'] }],
  plan_actual: [
    {
      numero_entrega: 1,
      fecha_entrega_planificada: null,
      estado: 'pendiente',
      items: [{ oc_item_id: 'item-1', cantidad_planificada: '40.00' }],
    },
  ],
}

const planificarOutCrudo = {
  orden_compra_id: 'oc-1',
  entregas: [
    {
      numero_entrega: 1,
      fecha_entrega_planificada: null,
      estado: 'pendiente',
      items: [{ oc_item_id: 'item-1', cantidad_planificada: '60.00' }],
    },
  ],
  advertencias: [
    {
      oc_item_id: 'item-1',
      numero_entrega: 1,
      cantidad: '30.00',
      unidades_por_presentacion: 25,
      cantidad_sugerida: '25.00',
    },
  ],
}

describe('cliente HTTP oc_entregas -- parseo de Decimal (fix de review)', () => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset())

  it('obtenerPlanificacionEntregas parsea `cantidad` y `cantidades` de string a number', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(planificacionCruda)

    const resultado = await obtenerPlanificacionEntregas('oc-1')

    expect(resultado.renglones[0].cantidad).toBe(100)
    expect(typeof resultado.renglones[0].cantidad).toBe('number')
    expect(resultado.plan_sugerido[0].cantidades).toEqual([50, 25, 25])
    expect(resultado.plan_actual[0].items[0].cantidad_planificada).toBe(40)
  })

  it('las cantidades parseadas suman con aritmética real, no concatenan strings', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(planificacionCruda)

    const resultado = await obtenerPlanificacionEntregas('oc-1')
    const suma = resultado.plan_sugerido[0].cantidades.reduce((acumulado, valor) => acumulado + valor, 0)

    expect(suma).toBe(100) // si concatenara strings, "50" + "25" + "25" -> "502525"
  })

  it('planificarEntregas parsea `cantidad_planificada` y las advertencias de la respuesta', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(planificarOutCrudo)

    const resultado = await planificarEntregas('oc-1', [
      { numero_entrega: 1, fecha_entrega_planificada: null, items: [{ oc_item_id: 'item-1', cantidad: 60 }] },
    ])

    expect(resultado.entregas[0].items[0].cantidad_planificada).toBe(60)
    expect(resultado.advertencias[0].cantidad).toBe(30)
    expect(resultado.advertencias[0].cantidad_sugerida).toBe(25)
  })

  it('planificarEntregas redondea a centavos antes de enviar (evita residuo binario en el body)', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValue(planificarOutCrudo)

    await planificarEntregas('oc-1', [
      {
        numero_entrega: 1,
        fecha_entrega_planificada: null,
        items: [{ oc_item_id: 'item-1', cantidad: 0.1 + 0.2 }], // 0.30000000000000004
      },
    ])

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/ordenes-compra/oc-1/entregas/planificacion',
      expect.objectContaining({
        body: JSON.stringify({
          entregas: [
            { numero_entrega: 1, fecha_entrega_planificada: null, items: [{ oc_item_id: 'item-1', cantidad: 0.3 }] },
          ],
        }),
      }),
    )
  })
})
