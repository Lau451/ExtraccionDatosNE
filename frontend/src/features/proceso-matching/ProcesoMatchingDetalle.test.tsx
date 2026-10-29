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

function fila(numero: number) {
  return screen.getByRole('row', { name: new RegExp(`^Renglón ${numero}\\b`) })
}

beforeEach(() => {
  vi.mocked(obtenerMatchingProceso).mockReset().mockResolvedValue(matching(RENGLONES))
  vi.mocked(confirmarMatching).mockReset().mockResolvedValue({})
  vi.mocked(marcarSinMatch).mockReset().mockResolvedValue({})
  vi.mocked(listarProductos).mockReset().mockResolvedValue({ items: [], total: 0 })
})

describe('ProcesoMatchingDetalle', () => {
  it('lists every renglón, including the automatic ones, with its estado and producto', async () => {
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)

    expect(
      await screen.findByRole('heading', {
        name: 'Matching de HOSPITAL SAN JOSE - LICITACION ACELERADA 16/26',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('Hospital San José · Licitación')).toBeInTheDocument()
    expect(screen.getByText('1 pendiente · 1 sugerido · 1 resuelto')).toBeInTheDocument()
    expect(obtenerMatchingProceso).toHaveBeenCalledWith('proc-1')

    expect(within(fila(1)).getByText('Sugerido 92%')).toBeInTheDocument()
    expect(within(fila(1)).getByText('Ibuprofeno 600mg x30')).toBeInTheDocument()
    expect(within(fila(2)).getByText('Automático')).toBeInTheDocument()
    expect(within(fila(2)).getByText('Amoxicilina 500mg x16')).toBeInTheDocument()
    expect(within(fila(3)).getByText('Pendiente')).toBeInTheDocument()
    expect(within(fila(3)).getByText('Sin candidatos')).toBeInTheDocument()
  })

  it('confirms the best candidato of a sugerido renglón in one click and reloads', async () => {
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    fireEvent.click(within(fila(1)).getByRole('button', { name: 'Confirmar sugerencia' }))

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-1', 'prod-ibu'))
    await waitFor(() => expect(obtenerMatchingProceso).toHaveBeenCalledTimes(2))
  })

  it('confirms another candidato of the renglón', async () => {
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    fireEvent.click(within(fila(1)).getByRole('button', { name: 'Elegir' }))
    const panel = screen.getByRole('region', { name: 'Elegir producto para el renglón 1' })
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Confirmar Ibuprofeno 400mg x20 (IBU400) 71%' }),
    )

    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-1', 'prod-ibu-400'))
  })

  it('confirms a producto found in the catalog when no candidato fits', async () => {
    vi.mocked(listarProductos).mockResolvedValue({
      items: [{ ...AMOXICILINA, id: 'prod-gasa', nombre: 'Gasa estéril 10x10 x100', codigo_interno: 'GAS10' }],
      total: 1,
    } as never)
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    fireEvent.click(within(fila(3)).getByRole('button', { name: 'Elegir' }))
    const panel = screen.getByRole('region', { name: 'Elegir producto para el renglón 3' })
    fireEvent.change(within(panel).getByPlaceholderText('Buscá en el catálogo por nombre o código'), {
      target: { value: 'gasa' },
    })

    fireEvent.click(
      await within(panel).findByRole('button', { name: 'Confirmar Gasa estéril 10x10 x100 (GAS10)' }),
    )

    expect(listarProductos).toHaveBeenCalledWith({ q: 'gasa', pageSize: 10 })
    await waitFor(() => expect(confirmarMatching).toHaveBeenCalledWith('item-3', 'prod-gasa'))
  })

  it('marks a renglón as sin match', async () => {
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    fireEvent.click(within(fila(3)).getByRole('button', { name: 'Elegir' }))
    fireEvent.click(screen.getByRole('button', { name: 'Marcar sin match' }))

    await waitFor(() => expect(marcarSinMatch).toHaveBeenCalledWith('item-3'))
  })

  it('lets a resolved renglón be changed', async () => {
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    expect(within(fila(2)).queryByRole('button', { name: 'Elegir' })).not.toBeInTheDocument()
    fireEvent.click(within(fila(2)).getByRole('button', { name: 'Cambiar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Marcar sin match' }))

    await waitFor(() => expect(marcarSinMatch).toHaveBeenCalledWith('item-2'))
  })

  it('shows the error when a decision fails and keeps the renglón as it was', async () => {
    vi.mocked(confirmarMatching).mockRejectedValue(new Error('El renglón no pertenece a tu droguería'))
    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)
    await screen.findByRole('heading', { name: /^Matching de/ })

    fireEvent.click(within(fila(1)).getByRole('button', { name: 'Confirmar sugerencia' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('El renglón no pertenece a tu droguería')
    expect(within(fila(1)).getByText('Sugerido 92%')).toBeInTheDocument()
    expect(obtenerMatchingProceso).toHaveBeenCalledTimes(1)
  })

  it('shows the load error', async () => {
    vi.mocked(obtenerMatchingProceso).mockRejectedValue(new Error('No se encontró el proceso comercial'))

    renderConQueryClient(<ProcesoMatchingDetalle procesoId="proc-1" />)

    expect(await screen.findByText('No se encontró el proceso comercial')).toBeInTheDocument()
  })
})
