import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompromisoEntrega } from '@/lib/api/compromisos'
import { ApiError } from '@/lib/api/presupuestacion'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, params }: { children?: React.ReactNode; to: string; params?: Record<string, string> }) => (
    <a href={to.replace('$ordenCompraId', params?.ordenCompraId ?? '')}>{children}</a>
  ),
}))
vi.mock('@/lib/api/compromisos', () => ({ listarCompromisos: vi.fn(), obtenerProximaFecha: vi.fn() }))

import { listarCompromisos, obtenerProximaFecha } from '@/lib/api/compromisos'
import { Compromisos } from './Compromisos'

// Sábado 17/10/2026 a media mañana en Buenos Aires.
const AHORA = new Date('2026-10-17T13:00:00Z')

function fila(o: Partial<CompromisoEntrega> = {}): CompromisoEntrega {
  return {
    drogueria_id: 'd1',
    orden_compra_id: 'oc-1',
    numero_oc: '4512',
    version_numero: 1,
    exportado_at: '2026-10-01T10:00:00Z',
    cliente: 'Htal. Garrahan',
    entrega_oc_id: 'e-1',
    numero_entrega: 1,
    fecha_entrega_planificada: '2026-10-20',
    numero_renglon: 1,
    codigo_articulo: 'A1',
    descripcion: 'Amoxicilina 500 mg',
    cantidad_planificada: 100,
    situacion: 'futura',
    dias_atraso: 0,
    posicion_en_plan: 1,
    entregas_en_plan: 2,
    ...o,
  }
}

const VENCIDAS = [
  fila({ entrega_oc_id: 'v-1', numero_oc: '4410', fecha_entrega_planificada: '2026-09-29', situacion: 'vencida', dias_atraso: 18 }),
  fila({ entrega_oc_id: 'v-2', numero_oc: '4471', cliente: 'Clínica Olivos', fecha_entrega_planificada: '2026-10-06', situacion: 'vencida', dias_atraso: 11 }),
]

const OCTUBRE = [
  fila({ entrega_oc_id: 'v-1', numero_oc: '4410', fecha_entrega_planificada: '2026-09-29', situacion: 'vencida', dias_atraso: 18 }),
  fila({ entrega_oc_id: 'v-2', numero_oc: '4471', cliente: 'Clínica Olivos', fecha_entrega_planificada: '2026-10-06', situacion: 'vencida', dias_atraso: 11 }),
  fila({ entrega_oc_id: 'f-1' }),
  ...['4471', '4520', '4523', '4524', '4530'].map((oc, i) =>
    fila({
      entrega_oc_id: `d23-${i}`,
      numero_oc: oc,
      cliente: i === 0 ? 'Clínica Olivos' : `Cliente ${oc}`,
      fecha_entrega_planificada: '2026-10-23',
    }),
  ),
]

function responderPorRango() {
  vi.mocked(listarCompromisos).mockImplementation(async (rango = {}) => {
    if (!rango.desde && rango.hasta) return VENCIDAS
    if (rango.desde === '2026-09-28') return OCTUBRE
    return []
  })
}

function renderPagina() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <Compromisos />
    </QueryClientProvider>,
  )
}

function dia(nombre: RegExp) {
  return screen.getByRole('button', { name: nombre })
}

describe('Compromisos (calendario)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(AHORA)
    vi.mocked(listarCompromisos).mockReset()
    vi.mocked(obtenerProximaFecha).mockReset().mockResolvedValue(null)
    responderPorRango()
  })

  afterEach(() => vi.useRealTimers())

  it('arranca en la vista Mes del mes actual y pide el rango visible y las vencidas', async () => {
    renderPagina()

    expect(screen.getByRole('heading', { name: 'Compromisos de entrega' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Mes' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('Octubre 2026')).toBeTruthy()
    await waitFor(() => expect(listarCompromisos).toHaveBeenCalledWith({ desde: '2026-09-28', hasta: '2026-11-01' }))
    expect(listarCompromisos).toHaveBeenCalledWith({ hasta: '2026-10-16' })
    expect(['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'].every((d) => screen.getByText(d))).toBe(true)
  })

  it('muestra hasta 3 chips por día y "+N más", con color por situación', async () => {
    renderPagina()

    const viernes = await waitFor(() => dia(/viernes 23 de octubre, 5 entregas/))
    const chips = within(viernes).getAllByTestId('chip-entrega')
    expect(chips).toHaveLength(3)
    expect(chips[0].textContent).toBe('4471 · Clínica Olivos')
    expect(within(viernes).getByText('+2 más')).toBeTruthy()
    const vencida = within(dia(/martes 6 de octubre, 1 entrega/)).getByTestId('chip-entrega')
    expect(vencida.getAttribute('data-situacion')).toBe('vencida')
  })

  it('marca hoy y atenúa los días de otro mes', async () => {
    renderPagina()

    const hoy = await waitFor(() => dia(/sábado 17 de octubre/))
    expect(hoy.getAttribute('aria-current')).toBe('date')
    expect(within(hoy).getByText('Hoy')).toBeTruthy()
    expect(dia(/lunes 28 de septiembre/).getAttribute('data-fuera-de-mes')).toBe('true')
    expect(dia(/jueves 1 de octubre/).getAttribute('data-fuera-de-mes')).toBe('false')
  })

  it('cuenta vencidas y entregas del mes (sin los días de otros meses)', async () => {
    renderPagina()

    expect(await screen.findByText('2 vencidas sin confirmar')).toBeTruthy()
    // 6/10, 20/10 y cinco el 23/10; la del 29/09 no es de octubre
    expect(await screen.findByText('7 entregas en octubre')).toBeTruthy()
  })

  it('navega de mes y vuelve con "Hoy"', async () => {
    renderPagina()
    await screen.findByText('7 entregas en octubre')

    fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }))
    expect(screen.getByText('Noviembre 2026')).toBeTruthy()
    await waitFor(() => expect(listarCompromisos).toHaveBeenCalledWith({ desde: '2026-10-26', hasta: '2026-12-06' }))

    fireEvent.click(screen.getByRole('button', { name: 'Mes anterior' }))
    fireEvent.click(screen.getByRole('button', { name: 'Mes anterior' }))
    expect(screen.getByText('Septiembre 2026')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    expect(screen.getByText('Octubre 2026')).toBeTruthy()
  })

  it('filtra los chips por cliente u OC', async () => {
    renderPagina()
    await waitFor(() => dia(/viernes 23 de octubre, 5 entregas/))

    fireEvent.change(screen.getByPlaceholderText('Buscar cliente u OC'), { target: { value: 'olivos' } })

    const viernes = dia(/viernes 23 de octubre, 1 entrega/)
    expect(within(viernes).getAllByTestId('chip-entrega')).toHaveLength(1)
    expect(dia(/martes 20 de octubre, 0 entregas/)).toBeTruthy()
  })

  it('la vista Lista muestra la agenda y oculta la navegación de período', async () => {
    renderPagina()

    fireEvent.click(screen.getByRole('button', { name: 'Lista' }))

    expect(screen.getByRole('button', { name: 'Lista' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('button', { name: 'Mes siguiente' })).toBeNull()
    expect(screen.queryByText('Octubre 2026')).toBeNull()
    await waitFor(() => expect(listarCompromisos).toHaveBeenCalledWith())
  })

  describe('panel lateral', () => {
    it('lista las 3 vencidas más viejas y "Ver las N" lleva a la Lista', async () => {
      vi.mocked(listarCompromisos).mockImplementation(async (rango = {}) => {
        if (!rango.desde && rango.hasta) {
          return [
            ...VENCIDAS,
            fila({ entrega_oc_id: 'v-3', numero_oc: '4488', fecha_entrega_planificada: '2026-10-13', situacion: 'vencida', dias_atraso: 4 }),
            fila({ entrega_oc_id: 'v-4', numero_oc: '4502', fecha_entrega_planificada: '2026-10-15', situacion: 'vencida', dias_atraso: 2 }),
          ]
        }
        return []
      })
      renderPagina()

      const panel = await screen.findByRole('region', { name: 'Vencidas sin confirmar' })
      const filas = within(panel).getAllByRole('listitem')
      expect(filas).toHaveLength(3)
      expect(filas[0].textContent).toContain('4410')
      expect(filas[0].textContent).toContain('29/09 · 18 días')
      expect(within(filas[0]).getByRole('link', { name: '4410' }).getAttribute('href')).toBe('/ordenes-compra/oc-1')

      fireEvent.click(within(panel).getByRole('button', { name: 'Ver las 4 vencidas →' }))
      expect(screen.getByRole('button', { name: 'Lista' }).getAttribute('aria-pressed')).toBe('true')
    })

    it('no muestra el bloque de vencidas si no hay', async () => {
      vi.mocked(listarCompromisos).mockImplementation(async (rango = {}) => (rango.desde === '2026-09-28' ? OCTUBRE : []))
      renderPagina()

      await screen.findByText('7 entregas en octubre')
      expect(screen.queryByRole('region', { name: 'Vencidas sin confirmar' })).toBeNull()
    })

    it('muestra el detalle del día elegido con "Entrega N de M" y sus renglones', async () => {
      renderPagina()

      const detalle = await screen.findByRole('region', { name: 'Detalle del día' })
      expect(within(detalle).getByText('17 de octubre')).toBeTruthy()
      expect(within(detalle).getByText('Sin entregas este día')).toBeTruthy()

      fireEvent.click(await waitFor(() => dia(/viernes 23 de octubre, 5 entregas/)))

      expect(within(detalle).getByText('viernes')).toBeTruthy()
      expect(within(detalle).getByText('23 de octubre')).toBeTruthy()
      expect(within(detalle).getByText('5 entregas · 5 renglones')).toBeTruthy()
      const entregas = within(detalle).getAllByRole('article')
      expect(entregas).toHaveLength(5)
      expect(within(entregas[0]).getByText('Clínica Olivos')).toBeTruthy()
      expect(within(entregas[0]).getByRole('link', { name: 'OC 4471' }).getAttribute('href')).toBe('/ordenes-compra/oc-1')
      expect(within(entregas[0]).getByText('Entrega 1 de 2')).toBeTruthy()
      expect(within(entregas[0]).getByText('Amoxicilina 500 mg')).toBeTruthy()
      expect(within(entregas[0]).getByText('100')).toBeTruthy()
    })

    it('muestra 3 renglones por entrega y despliega el resto', async () => {
      vi.mocked(listarCompromisos).mockImplementation(async (rango = {}) =>
        rango.desde === '2026-09-28'
          ? [1, 2, 3, 4, 5].map((n) =>
              fila({ fecha_entrega_planificada: '2026-10-17', numero_renglon: n, descripcion: `Renglón ${n}` }),
            )
          : [],
      )
      renderPagina()

      const detalle = await screen.findByRole('region', { name: 'Detalle del día' })
      await within(detalle).findByText('Renglón 1')
      expect(within(detalle).queryByText('Renglón 4')).toBeNull()

      fireEvent.click(within(detalle).getByRole('button', { name: '+2 renglones' }))
      expect(within(detalle).getByText('Renglón 5')).toBeTruthy()
    })
  })

  describe('estados', () => {
    it('muestra la grilla en carga mientras llega el período', () => {
      vi.mocked(listarCompromisos).mockReturnValue(new Promise(() => {}))
      renderPagina()

      expect(screen.getByRole('status').textContent).toContain('Cargando compromisos')
    })

    it('mes vacío: ofrece ir a la próxima fecha con compromisos', async () => {
      vi.mocked(obtenerProximaFecha).mockResolvedValue('2026-12-02')
      renderPagina()
      await screen.findByText('7 entregas en octubre')

      fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }))

      expect(await screen.findByText('No hay entregas en noviembre')).toBeTruthy()
      expect(screen.getByText(/Las entregas aparecen cuando una OC se exporta a Progress/)).toBeTruthy()
      expect(await screen.findByText(/La próxima está el 2 de diciembre/)).toBeTruthy()
      expect(obtenerProximaFecha).toHaveBeenCalledWith('2026-11-30')

      fireEvent.click(screen.getByRole('button', { name: 'Ir a diciembre' }))
      expect(screen.getByText('Diciembre 2026')).toBeTruthy()
      expect(within(screen.getByRole('region', { name: 'Detalle del día' })).getByText('2 de diciembre')).toBeTruthy()
    })

    it('mes vacío sin compromisos más adelante: no ofrece navegar', async () => {
      renderPagina()
      await screen.findByText('7 entregas en octubre')

      fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }))

      expect(await screen.findByText('No hay entregas en noviembre')).toBeTruthy()
      await waitFor(() => expect(obtenerProximaFecha).toHaveBeenCalled())
      expect(screen.queryByRole('button', { name: /^Ir a / })).toBeNull()
    })

    it('búsqueda sin coincidencias: lo dice y no busca la próxima fecha', async () => {
      renderPagina()
      await screen.findByText('7 entregas en octubre')

      fireEvent.change(screen.getByPlaceholderText('Buscar cliente u OC'), { target: { value: 'zzz' } })

      expect(screen.getByText('Ninguna entrega coincide con la búsqueda')).toBeTruthy()
      expect(obtenerProximaFecha).not.toHaveBeenCalled()
    })

    it('error: muestra el mensaje y reintenta', async () => {
      vi.mocked(listarCompromisos).mockImplementation(async (rango = {}) => {
        if (rango.desde) throw new ApiError('Servicio no disponible', 503)
        return []
      })
      renderPagina()

      expect(await screen.findByText('No se pudieron cargar los compromisos')).toBeTruthy()
      expect(screen.getByText('Servicio no disponible')).toBeTruthy()
      const llamadas = vi.mocked(listarCompromisos).mock.calls.filter(([r]) => r?.desde).length

      fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
      await waitFor(() =>
        expect(vi.mocked(listarCompromisos).mock.calls.filter(([r]) => r?.desde).length).toBe(llamadas + 1),
      )
    })
  })
})
