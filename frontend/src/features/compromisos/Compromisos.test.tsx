import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompromisoEntrega } from '@/lib/api/compromisos'

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
})
