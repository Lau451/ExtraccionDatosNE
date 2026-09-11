import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { MockApiError } = vi.hoisted(() => ({
  MockApiError: class extends Error {
    status: number

    constructor(message: string, status: number) {
      super(message)
      this.status = status
    }
  },
}))

vi.mock('./presupuestacion', () => ({ presupuestacionFetch: vi.fn(), ApiError: MockApiError }))

const { getSessionMock } = vi.hoisted(() => ({ getSessionMock: vi.fn() }))
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: getSessionMock } } }))

import { presupuestacionFetch } from './presupuestacion'
import {
  actualizarSeleccion, cambiarEstadoPcp, cerrarPcp, crearPcp, listarPcp, listarSeleccionesAgrupables, obtenerPcp,
  obtenerResultado, registrarResultado, seleccionarProveedores,
} from './pcp'
import * as pcpClient from './pcp'
import { pcpQueryKeys } from '@/features/pcp/queryKeys'

const crearRenglon = (pcpClient as unknown as {
  crearRenglon: (pcpId: string, payload: { item_proceso_id: string, origen?: string, regla_pcp_id?: string }) => Promise<unknown>
}).crearRenglon

// Consultas (6.1 RED): los métodos aún no existen en pcp.ts. El acceso vía
// el módulo importado, con el mismo cast que `crearRenglon` usó en 4.1,
// garantiza el fallo RED (propiedad `undefined` no invocable) sin romper la
// compilación de este archivo de test.
interface SeleccionParaAgrupar {
  pcp_renglon_id: string
  proveedor_id: string
  cantidad_consultada?: number
}
interface AgruparConsultaPayload {
  selecciones: SeleccionParaAgrupar[]
  contacto_id?: string
  fecha_respuesta_esperada?: string
  canal?: string
}
const agruparConsultas = (pcpClient as unknown as {
  agruparConsultas: (payload: AgruparConsultaPayload) => Promise<unknown[]>
}).agruparConsultas

const obtenerConsulta = (pcpClient as unknown as {
  obtenerConsulta: (consultaId: string) => Promise<unknown>
}).obtenerConsulta

const enviarConsulta = (pcpClient as unknown as {
  enviarConsulta: (consultaId: string) => Promise<unknown>
}).enviarConsulta

const descargarPdfConsulta = (pcpClient as unknown as {
  descargarPdfConsulta: (consultaId: string) => Promise<Blob>
}).descargarPdfConsulta

const pcp = {
  id: 'pcp-1',
  drogueria_id: 'drog-1',
  presupuesto_id: 'pres-1',
  proceso_comercial_id: 'proc-1',
  estado: 'nueva' as const,
  fecha_entrega_solicitada: null,
  solicitante_id: null,
  sector_id: null,
  origen: 'manual',
  regla_pcp_id: null,
  notas: null,
  cerrada_at: null,
  cerrada_por: null,
}

describe('cliente PCP', () => {
  beforeEach(() => vi.mocked(presupuestacionFetch).mockReset().mockResolvedValue(pcp))

  it('envía filtros de listado solo cuando están presentes', async () => {
    await listarPcp({ estado: 'en_gestion', fecha_desde: '2026-01-01' })

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp?estado=en_gestion&fecha_desde=2026-01-01')
  })

  it('conserva una clave de familia para todas las listas, incluidas las filtradas', () => {
    expect(pcpQueryKeys.listas()).toEqual(['pcp'])
    expect(pcpQueryKeys.lista()).toEqual(['pcp'])
    expect(pcpQueryKeys.lista({ estado: 'cerrada' })).toEqual(['pcp', { estado: 'cerrada' }])
  })

  it('omite filtros vacíos, serializa fecha_hasta y obtiene el detalle por id', async () => {
    await listarPcp()
    await listarPcp({ fecha_hasta: '2026-12-31' })
    await obtenerPcp('pcp-1')

    expect(presupuestacionFetch).toHaveBeenNthCalledWith(1, '/pcp')
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(2, '/pcp?fecha_hasta=2026-12-31')
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(3, '/pcp/pcp-1')
  })

  it('crea PCP y aplica las transiciones y el cierre en sus rutas exactas', async () => {
    await crearPcp({ presupuesto_id: 'pres-1', notas: 'Urgente' })
    await cambiarEstadoPcp('pcp-1', 'en_gestion')
    await cerrarPcp('pcp-1')

    expect(presupuestacionFetch).toHaveBeenNthCalledWith(1, '/pcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presupuesto_id: 'pres-1', notas: 'Urgente' }),
    })
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(2, '/pcp/pcp-1/estado', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estado: 'en_gestion' }),
    })
    expect(presupuestacionFetch).toHaveBeenNthCalledWith(3, '/pcp/pcp-1/cerrar', { method: 'POST' })
  })

  it('crea un renglón con solamente item_proceso_id', async () => {
    await crearRenglon('pcp-1', { item_proceso_id: 'item-1' })

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/pcp-1/renglones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_proceso_id: 'item-1' }),
    })
  })

  it('conserva origen y regla_pcp_id opcionales sin agregar campos prohibidos', async () => {
    await crearRenglon('pcp-1', {
      item_proceso_id: 'item-1', origen: 'regla', regla_pcp_id: 'regla-1',
    })

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/pcp-1/renglones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_proceso_id: 'item-1', origen: 'regla', regla_pcp_id: 'regla-1' }),
    })
  })

  it('normaliza el detalle FastAPI 422 en un mensaje de validación legible', async () => {
    const fastApi422 = Object.create(MockApiError.prototype) as Error & { status: number, message: unknown }
    fastApi422.status = 422
    Object.defineProperty(fastApi422, 'message', {
      value: [{ loc: ['body', 'item_proceso_id'], msg: 'Field required', type: 'missing' }],
    })

    await expect(Promise.resolve().then(() => {
      if (typeof crearRenglon === 'function') {
        vi.mocked(presupuestacionFetch).mockImplementationOnce(async () => { throw fastApi422 })
      }
      return crearRenglon('pcp-1', { item_proceso_id: '' })
    })).rejects.toMatchObject({
      status: 422,
      message: 'item_proceso_id: Field required',
    })
  })

  it('normaliza el detalle FastAPI 422 en un mensaje de validación legible para la selección de proveedores', async () => {
    const fastApi422 = Object.create(MockApiError.prototype) as Error & { status: number, message: unknown }
    fastApi422.status = 422
    Object.defineProperty(fastApi422, 'message', {
      value: [{ loc: ['body', 'proveedor_ids'], msg: 'Field required', type: 'missing' }],
    })
    vi.mocked(presupuestacionFetch).mockRejectedValueOnce(fastApi422)

    await expect(seleccionarProveedores('pcp-1', 'reng-1', [])).rejects.toMatchObject({
      status: 422,
      message: 'proveedor_ids: Field required',
    })
  })

  it('envía exactamente {seleccionado} al actualizar la selección de un proveedor', async () => {
    await actualizarSeleccion('pcp-1', 'reng-1', 'prov-1', true)

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/pcp/pcp-1/renglones/reng-1/proveedores/prov-1/seleccion',
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seleccionado: true }),
      },
    )
  })

  it('obtiene los pares renglón×proveedor agrupables de todo el PCP por su ruta exacta', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValueOnce([
      { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
      { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
    ])

    const resultado = await listarSeleccionesAgrupables('pcp-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/pcp-1/selecciones-agrupables')
    expect(resultado).toEqual([
      { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
      { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
    ])
  })

  it('obtiene el resultado de un proveedor por su ruta exacta', async () => {
    await obtenerResultado('pcp-1', 'reng-1', 'prov-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/pcp/pcp-1/renglones/reng-1/proveedores/prov-1/resultado',
    )
  })

  it('propaga un 404 de obtenerResultado como ApiError sin tragárselo en esta capa', async () => {
    const noEncontrado = Object.create(MockApiError.prototype) as Error & { status: number, message: unknown }
    noEncontrado.status = 404
    Object.defineProperty(noEncontrado, 'message', { value: 'No encontrado' })
    vi.mocked(presupuestacionFetch).mockRejectedValueOnce(noEncontrado)

    await expect(obtenerResultado('pcp-1', 'reng-1', 'prov-1')).rejects.toMatchObject({ status: 404 })
  })

  it('registra un resultado precio_obtenido con los campos opcionales relevantes', async () => {
    await registrarResultado('pcp-1', 'reng-1', 'prov-1', {
      resultado: 'precio_obtenido',
      precio_unitario: 10.5,
      cantidad_minima: 1,
      cantidad_maxima: 100,
      mantenimiento_hasta: '2026-12-31',
      condicion_pago_id: 'cond-1',
      forma_pago_id: 'forma-1',
      notas: 'Nota interna',
    })

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/pcp/pcp-1/renglones/reng-1/proveedores/prov-1/resultado',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resultado: 'precio_obtenido',
          precio_unitario: 10.5,
          cantidad_minima: 1,
          cantidad_maxima: 100,
          mantenimiento_hasta: '2026-12-31',
          condicion_pago_id: 'cond-1',
          forma_pago_id: 'forma-1',
          notas: 'Nota interna',
        }),
      },
    )
  })

  it('registra un resultado no_cotiza con un cuerpo mínimo, sin campos de precio', async () => {
    await registrarResultado('pcp-1', 'reng-1', 'prov-1', { resultado: 'no_cotiza', motivo: 'Sin stock' })

    expect(presupuestacionFetch).toHaveBeenCalledWith(
      '/pcp/pcp-1/renglones/reng-1/proveedores/prov-1/resultado',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resultado: 'no_cotiza', motivo: 'Sin stock' }),
      },
    )
  })

  it('normaliza el detalle FastAPI 422 al registrar un resultado', async () => {
    const fastApi422 = Object.create(MockApiError.prototype) as Error & { status: number, message: unknown }
    fastApi422.status = 422
    Object.defineProperty(fastApi422, 'message', {
      value: [{ loc: ['body', 'precio_unitario'], msg: 'Field required', type: 'missing' }],
    })
    vi.mocked(presupuestacionFetch).mockRejectedValueOnce(fastApi422)

    await expect(registrarResultado('pcp-1', 'reng-1', 'prov-1', {
      resultado: 'precio_obtenido',
    })).rejects.toMatchObject({
      status: 422,
      message: 'precio_unitario: Field required',
    })
  })

  it('agrupa selecciones de renglones de varios proveedores en una consulta por proveedor distinto', async () => {
    vi.mocked(presupuestacionFetch).mockResolvedValueOnce([
      {
        id: 'consulta-1', drogueria_id: 'drog-1', proveedor_id: 'prov-1', contacto_id: null,
        estado: 'borrador', canal: null, fecha_envio: null, fecha_respuesta_esperada: null, documento_path: null,
      },
      {
        id: 'consulta-2', drogueria_id: 'drog-1', proveedor_id: 'prov-2', contacto_id: null,
        estado: 'borrador', canal: null, fecha_envio: null, fecha_respuesta_esperada: null, documento_path: null,
      },
    ])

    const selecciones = [
      { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
      { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
      { pcp_renglon_id: 'reng-3', proveedor_id: 'prov-2' },
    ]
    const resultado = await agruparConsultas({ selecciones })

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/consultas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selecciones }),
    })
    expect(resultado).toHaveLength(2)
  })

  it('obtiene una consulta agrupada por su id exacto', async () => {
    await obtenerConsulta('consulta-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/consultas/consulta-1')
  })

  it('envía una consulta agrupada por su ruta exacta', async () => {
    await enviarConsulta('consulta-1')

    expect(presupuestacionFetch).toHaveBeenCalledWith('/pcp/consultas/consulta-1/enviar', { method: 'POST' })
  })
})

describe('descargarPdfConsulta (descarga binaria)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    getSessionMock.mockReset().mockResolvedValue({ data: { session: { access_token: 'token-abc' } } })
    // Test-authoring defect fix (documented in apply-progress.md, Work Unit 6.2):
    // without this reset, `presupuestacionFetch`'s call history leaks in from
    // the preceding `cliente PCP` describe (same file, same mock instance),
    // making `expect(presupuestacionFetch).not.toHaveBeenCalled()` below fail
    // under any correct implementation.
    vi.mocked(presupuestacionFetch).mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('descarga el PDF como blob binario con el header de autorización, sin pasar por presupuestacionFetch', async () => {
    const blobFalso = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    fetchMock.mockResolvedValue({ ok: true, blob: vi.fn().mockResolvedValue(blobFalso) })

    const resultado = await descargarPdfConsulta('consulta-1')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/pcp/consultas/consulta-1/pdf'),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-abc' }),
      }),
    )
    expect(resultado).toBe(blobFalso)
    expect(presupuestacionFetch).not.toHaveBeenCalled()
  })

  it('rechaza cuando la respuesta del PDF no es exitosa, sin intentar parsear JSON', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, blob: vi.fn() })

    await expect(descargarPdfConsulta('consulta-inexistente')).rejects.toBeTruthy()
  })
})
