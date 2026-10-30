import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MatchingProceso, RenglonMatching } from '@/lib/api/matching'
import { ProcesoMatchingDetalle } from './ProcesoMatchingDetalle'

vi.mock('@/lib/api/matching', () => ({
  obtenerMatchingProceso: vi.fn(),
  confirmarMatching: vi.fn(),
  marcarSinMatch: vi.fn(),
}))

vi.mock('@/lib/api/productos', () => ({
  listarProductos: vi.fn(),
}))

import { confirmarMatching, marcarSinMatch, obtenerMatchingProceso } from '@/lib/api/matching'
import { listarProductos } from '@/lib/api/productos'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const IBUPROFENO = { id: 'prod-ibu', nombre: 'Ibuprofeno 600mg x30', codigo_interno: 'IBU600' }
const IBUPROFENO_400 = { id: 'prod-ibu-400', nombre: 'Ibuprofeno 400mg x20', codigo_interno: 'IBU400' }
const AMOXICILINA = { id: 'prod-amox', nombre: 'Amoxicilina 500mg x16', codigo_interno: 'AMX500' }
const GASA = { id: 'prod-gasa', nombre: 'Gasa estéril 10x10 x100', codigo_interno: 'GAS10' }

function renglon(overrides: Partial<RenglonMatching> = {}): RenglonMatching {
  return {
    item_proceso_id: 'item-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 600 mg comp x 30',
    cantidad: '100.00',
    estado_matching: 'sugerido',
    confianza_matching: '92.00',
    producto: null,
    candidatos: [
      { producto: IBUPROFENO, confianza: '92.00', metodo: 'fuzzy', elegido: false },
      { producto: IBUPROFENO_400, confianza: '71.00', metodo: 'fuzzy', elegido: false },
    ],
    ...overrides,
  }
}

function matching(renglones: RenglonMatching[]): MatchingProceso {
  return {
    proceso_comercial_id: 'proc-1',
    nombre: 'HOSPITAL SAN JOSE - LICITACION ACELERADA 16/26',
    clase: 'licitacion',
    cliente: 'Hospital San José',
    renglones,
  }
}

const RENGLONES = [
  renglon(),
  renglon({
    item_proceso_id: 'item-2',
    numero_renglon: 2,
    descripcion: 'Amoxicilina 500',
    estado_matching: 'automatico',
    confianza_matching: null,
    producto: AMOXICILINA,
    candidatos: [],
  }),
  renglon({
    item_proceso_id: 'item-3',
    numero_renglon: 3,
    descripcion: 'Gasa estéril 10x10',
    estado_matching: 'pendiente',
    confianza_matching: null,
    candidatos: [],
  }),
]

function cola() {
  return screen.getByRole('listbox', { name: 'Renglones del proceso' })
}

function opcion(numero: number) {
  return within(cola()).getByRole('option', { name: `Renglón ${numero}` })
}

function panel() {
  return screen.getByRole('region', { name: 'Renglón elegido' })
}

function buscador() {
  return screen.getByRole('textbox', { name: 'Buscar otro producto en el catálogo' })
}

async function abrir() {
  renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
  await screen.findByRole('heading', { name: /^Matching de/ })
}

beforeEach(() => {
  vi.mocked(obtenerMatchingProceso).mockReset().mockResolvedValue(matching(RENGLONES))
  vi.mocked(confirmarMatching).mockReset().mockResolvedValue({})
  vi.mocked(marcarSinMatch).mockReset().mockResolvedValue({})
  vi.mocked(listarProductos).mockReset().mockResolvedValue({ items: [], total: 0 })
})

describe('ProcesoMatchingDetalle', () => {
  it('shows the header, the progress and the queue of renglones still to resolve', async () => {
    await abrir()

    expect(
      screen.getByRole('heading', { name: 'Matching de HOSPITAL SAN JOSE - LICITACION ACELERADA 16/26' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Hospital San José · Licitación · 3 renglones')).toBeInTheDocument()
    expect(screen.getByText('1 de 3 resueltos')).toBeInTheDocument()
    expect(obtenerMatchingProceso).toHaveBeenCalledWith('proc-1')

    expect(within(cola()).getAllByRole('option')).toHaveLength(2)
    expect(within(opcion(1)).getByText('Sugerido 92%')).toBeInTheDocument()
    expect(within(opcion(1)).getByText('Ibuprofeno 600mg x30')).toBeInTheDocument()
    expect(within(opcion(3)).getByText('Pendiente')).toBeInTheDocument()
    expect(within(opcion(3)).getByText('Sin candidatos')).toBeInTheDocument()
    expect(opcion(1)).toHaveAttribute('aria-selected', 'true')
    expect(within(panel()).getByRole('heading', { name: 'Ibuprofeno 600 mg comp x 30' })).toBeInTheDocument()
  })

  it('shows the automatic renglones under Todos and Resueltos', async () => {
    await abrir()

    fireEvent.click(screen.getByRole('button', { name: 'Todos' }))
    expect(within(cola()).getAllByRole('option')).toHaveLength(3)
    expect(within(opcion(2)).getByText('Automático')).toBeInTheDocument()
    expect(within(opcion(2)).getByText('Amoxicilina 500mg x16')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Resueltos' }))
    expect(within(cola()).getAllByRole('option')).toHaveLength(1)
  })

  it('Enter confirms the best candidato and moves on to the next renglón right away', async () => {
    const confirmado = renglon({ estado_matching: 'confirmado', producto: IBUPROFENO })
    vi.mocked(obtenerMatchingProceso)
      .mockResolvedValueOnce(matching(RENGLONES))
      .mockResolvedValue(matching([confirmado, RENGLONES[1], RENGLONES[2]]))
    await abrir()

    fireEvent.keyDown(document.body, { key: 'Enter' })

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-1', 'prod-ibu'))
    expect(within(panel()).getByRole('heading', { name: 'Gasa estéril 10x10' })).toBeInTheDocument()
    expect(within(cola()).queryByRole('option', { name: 'Renglón 1' })).not.toBeInTheDocument()
    await waitFor(() => expect(obtenerMatchingProceso).toHaveBeenCalledTimes(2))
  })

  it('a number key confirms that candidato', async () => {
    await abrir()

    fireEvent.keyDown(document.body, { key: '2' })

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-1', 'prod-ibu-400'))
  })

  it('clicking a candidato confirms it', async () => {
    await abrir()

    fireEvent.click(
      within(panel()).getByRole('button', { name: 'Confirmar Ibuprofeno 400mg x20 (IBU400) 71%' }),
    )

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-1', 'prod-ibu-400'))
  })

  it('Shift pressed alone marks the renglón sin match; Shift with another key does not', async () => {
    await abrir()

    fireEvent.keyDown(document.body, { key: 'Shift', shiftKey: true })
    fireEvent.keyDown(document.body, { key: 'A', shiftKey: true })
    fireEvent.keyUp(document.body, { key: 'Shift' })
    expect(marcarSinMatch).not.toHaveBeenCalled()

    fireEvent.keyDown(document.body, { key: 'Shift', shiftKey: true })
    fireEvent.keyUp(document.body, { key: 'Shift' })

    await waitFor(() => expect(marcarSinMatch).toHaveBeenCalledWith('item-1'))
  })

  it('the Sin match button marks the renglón sin match', async () => {
    await abrir()

    fireEvent.click(within(panel()).getByRole('button', { name: 'Marcar sin match' }))

    await waitFor(() => expect(marcarSinMatch).toHaveBeenCalledWith('item-1'))
  })

  it('typing a letter goes to the catalog search instead of triggering a shortcut', async () => {
    await abrir()

    fireEvent.keyDown(document.body, { key: 's' })

    expect(buscador()).toHaveFocus()
    expect(buscador()).toHaveValue('s')
    expect(marcarSinMatch).not.toHaveBeenCalled()
    expect(confirmarMatching).not.toHaveBeenCalled()
  })

  it('keys typed in the search never trigger shortcuts, and Tab goes back to the renglones', async () => {
    await abrir()
    buscador().focus()

    fireEvent.keyDown(buscador(), { key: '1' })
    fireEvent.keyDown(buscador(), { key: 'Shift', shiftKey: true })
    fireEvent.keyUp(buscador(), { key: 'Shift' })
    expect(confirmarMatching).not.toHaveBeenCalled()
    expect(marcarSinMatch).not.toHaveBeenCalled()

    fireEvent.keyDown(buscador(), { key: 'Tab' })
    expect(cola()).toHaveFocus()
  })

  it('confirms the first producto found in the catalog with Enter', async () => {
    vi.mocked(listarProductos).mockResolvedValue({ items: [GASA], total: 1 } as never)
    await abrir()
    fireEvent.click(opcion(3))

    fireEvent.change(buscador(), { target: { value: 'gasa' } })
    await within(panel()).findByRole('option', { name: 'Confirmar Gasa estéril 10x10 x100 (GAS10)' })
    expect(listarProductos).toHaveBeenCalledWith({ q: 'gasa', pageSize: 10 })

    fireEvent.keyDown(buscador(), { key: 'Enter' })
    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-3', 'prod-gasa'))
  })

  it('arrow keys move between the catalog results and Enter confirms the marked one', async () => {
    const GASA_20 = { id: 'prod-gasa-20', nombre: 'Gasa estéril 20x20 x50', codigo_interno: 'GAS20' }
    vi.mocked(listarProductos).mockResolvedValue({ items: [GASA, GASA_20], total: 2 } as never)
    await abrir()
    fireEvent.click(opcion(3))

    fireEvent.change(buscador(), { target: { value: 'gasa' } })
    const resultados = await within(panel()).findByRole('listbox', { name: 'Resultados del catálogo' })
    expect(within(resultados).getByRole('option', { name: /Gasa estéril 10x10/ })).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(buscador(), { key: 'ArrowDown' })
    expect(within(resultados).getByRole('option', { name: /Gasa estéril 20x20/ })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(buscador(), { key: 'ArrowDown' })
    fireEvent.keyDown(buscador(), { key: 'ArrowUp' })
    fireEvent.keyDown(buscador(), { key: 'ArrowDown' })
    expect(opcion(3)).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(buscador(), { key: 'Enter' })
    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-3', 'prod-gasa-20'))
    expect(confirmarMatching).toHaveBeenCalledTimes(1)
  })

  it('the search is labeled Catálogo and turns off the browser autocomplete', async () => {
    await abrir()

    expect(within(panel()).getByText('Catálogo')).toBeInTheDocument()
    expect(within(panel()).queryByText(/Otro producto|empezá a escribir/i)).not.toBeInTheDocument()
    expect(buscador()).toHaveAttribute('autocomplete', 'off')
  })

  it('clicking a producto found in the catalog confirms it', async () => {
    vi.mocked(listarProductos).mockResolvedValue({ items: [GASA], total: 1 } as never)
    await abrir()
    fireEvent.click(opcion(3))

    fireEvent.change(buscador(), { target: { value: 'gasa' } })
    fireEvent.click(
      await within(panel()).findByRole('option', { name: 'Confirmar Gasa estéril 10x10 x100 (GAS10)' }),
    )

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-3', 'prod-gasa'))
  })

  it('arrow keys and clicks choose the renglón of the panel', async () => {
    await abrir()

    fireEvent.keyDown(document.body, { key: 'ArrowDown' })
    expect(opcion(3)).toHaveAttribute('aria-selected', 'true')
    expect(within(panel()).getByRole('heading', { name: 'Gasa estéril 10x10' })).toBeInTheDocument()

    fireEvent.keyDown(document.body, { key: 'ArrowUp' })
    expect(opcion(1)).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(opcion(3))
    expect(opcion(3)).toHaveAttribute('aria-selected', 'true')
  })

  it('a resolved renglón can be changed', async () => {
    await abrir()
    fireEvent.click(screen.getByRole('button', { name: 'Resueltos' }))
    fireEvent.click(opcion(2))

    fireEvent.click(within(panel()).getByRole('button', { name: 'Marcar sin match' }))

    await waitFor(() => expect(marcarSinMatch).toHaveBeenCalledWith('item-2'))
  })

  it('Ctrl+Z goes back to the last decided renglón', async () => {
    await abrir()
    fireEvent.keyDown(document.body, { key: 'Enter' })
    await waitFor(() => expect(confirmarMatching).toHaveBeenCalled())

    expect(screen.getByRole('status')).toHaveTextContent('Renglón 1: Ibuprofeno 600mg x30')
    fireEvent.keyDown(document.body, { key: 'z', ctrlKey: true })

    expect(within(panel()).getByRole('heading', { name: 'Ibuprofeno 600 mg comp x 30' })).toBeInTheDocument()
    expect(buscador()).not.toHaveFocus()
  })

  it('shows the error when a decision fails and puts the renglón back as it was', async () => {
    vi.mocked(confirmarMatching).mockRejectedValue(new Error('El renglón no pertenece a tu droguería'))
    await abrir()

    fireEvent.keyDown(document.body, { key: 'Enter' })

    expect(await screen.findByRole('alert')).toHaveTextContent('El renglón no pertenece a tu droguería')
    expect(within(opcion(1)).getByText('Sugerido 92%')).toBeInTheDocument()
    expect(screen.getByText('1 de 3 resueltos')).toBeInTheDocument()
  })

  it('says so when no renglón is left to resolve', async () => {
    vi.mocked(obtenerMatchingProceso).mockResolvedValue(matching([RENGLONES[1]]))
    await abrir()

    expect(screen.getByText('No quedan renglones por resolver.')).toBeInTheDocument()
  })

  it('shows the load error', async () => {
    vi.mocked(obtenerMatchingProceso).mockRejectedValue(new Error('No se encontró el proceso comercial'))

    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)

    expect(await screen.findByText('No se encontró el proceso comercial')).toBeInTheDocument()
  })
})
