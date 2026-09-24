import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MatchingOut, PresupuestosCandidatosOut, RenglonOrdenCompra } from '@/lib/api/ocMatching'
import { OcMatchingDetalle } from './OcMatchingDetalle'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/api/ocMatching', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/ocMatching')>('@/lib/api/ocMatching')
  return {
    ...actual,
    obtenerPresupuestosCandidatos: vi.fn(),
    obtenerMatching: vi.fn(),
    confirmarVinculo: vi.fn(),
    deshacerVinculo: vi.fn(),
    descartarRenglon: vi.fn(),
  }
})

import {
  confirmarVinculo,
  deshacerVinculo,
  descartarRenglon,
  obtenerMatching,
  obtenerPresupuestosCandidatos,
} from '@/lib/api/ocMatching'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const CANDIDATOS_VACIO: PresupuestosCandidatosOut = {
  orden_compra_id: 'oc-1',
  cliente_id: 'cli-1',
  razon_social_cliente: 'Hospital Central',
  presupuestos_del_cliente: 0,
  candidatos: [],
  presupuesto_sugerido_id: null,
  advertencias: [],
}

function renglonOc(overrides: Partial<RenglonOrdenCompra> = {}): RenglonOrdenCompra {
  return {
    oc_item_id: 'item-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad: 10,
    precio_unitario: 1250,
    producto_id: null,
    estado: 'pendiente',
    presupuesto_item_id: null,
    vinculo_origen: null,
    candidatos: [{ presupuesto_item_id: 'pi-1', similitud: null }],
    ...overrides,
  }
}

function matching(overrides: Partial<MatchingOut> = {}): MatchingOut {
  return {
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-100',
    cliente_id: 'cli-1',
    presupuesto_id: 'pre-1',
    renglones_presupuesto: [],
    renglones_oc: [
      renglonOc(),
      renglonOc({
        oc_item_id: 'item-2',
        numero_renglon: 2,
        descripcion: 'Paracetamol 500mg x 10',
        precio_unitario: 500,
        candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }],
      }),
    ],
    advertencias: [],
    ...overrides,
  }
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(obtenerPresupuestosCandidatos).mockReset().mockResolvedValue(CANDIDATOS_VACIO)
  vi.mocked(obtenerMatching).mockReset()
  vi.mocked(confirmarVinculo).mockReset()
  vi.mocked(deshacerVinculo).mockReset()
  vi.mocked(descartarRenglon).mockReset()
})

describe('OcMatchingDetalle (design.md D12/D13)', () => {
  it('confirmar un renglón dispara una sola mutación, reemplaza la cache sin refetch y no toca los demás renglones', async () => {
    vi.mocked(obtenerMatching).mockResolvedValue(matching())
    vi.mocked(confirmarVinculo).mockResolvedValue(
      matching({
        renglones_oc: [
          renglonOc({
            estado: 'confirmado',
            presupuesto_item_id: 'pi-1',
            vinculo_origen: 'precio_exacto',
            candidatos: [],
          }),
          renglonOc({
            oc_item_id: 'item-2',
            numero_renglon: 2,
            descripcion: 'Paracetamol 500mg x 10',
            precio_unitario: 500,
            candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }],
          }),
        ],
      }),
    )

    renderConQueryClient(<OcMatchingDetalle ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg x 20')
    fireEvent.click(screen.getAllByRole('button', { name: /^confirmar$/i })[0])

    await waitFor(() => expect(confirmarVinculo).toHaveBeenCalledTimes(1))
    expect(confirmarVinculo).toHaveBeenCalledWith('oc-1', 'item-1', 'pi-1')

    await waitFor(() => expect(screen.getByText(/precio exacto/i)).toBeInTheDocument())
    // Sin refetch (D13): obtenerMatching solo se llamó en el montaje inicial;
    // la cache se reemplazó directamente con el MatchingOut de la mutación.
    expect(obtenerMatching).toHaveBeenCalledTimes(1)

    // El segundo renglón permanece sin cambios, disponible para confirmarse.
    expect(screen.getByText('Paracetamol 500mg x 10')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^confirmar$/i })).toHaveLength(1)
  })

  it('deshacer reemplaza la cache con el MatchingOut devuelto por la mutación, sin refetch', async () => {
    vi.mocked(obtenerMatching).mockResolvedValue(
      matching({
        renglones_oc: [
          renglonOc({
            estado: 'confirmado',
            presupuesto_item_id: 'pi-1',
            vinculo_origen: 'precio_exacto',
            candidatos: [],
          }),
          renglonOc({
            oc_item_id: 'item-2',
            numero_renglon: 2,
            descripcion: 'Paracetamol 500mg x 10',
            precio_unitario: 500,
            candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }],
          }),
        ],
      }),
    )
    vi.mocked(deshacerVinculo).mockResolvedValue(matching())

    renderConQueryClient(<OcMatchingDetalle ordenCompraId="oc-1" />)

    await screen.findByRole('button', { name: /^deshacer$/i })
    fireEvent.click(screen.getByRole('button', { name: /^deshacer$/i }))

    await waitFor(() => expect(deshacerVinculo).toHaveBeenCalledWith('oc-1', 'item-1'))
    await waitFor(() => expect(screen.getAllByRole('button', { name: /^confirmar$/i })).toHaveLength(2))
    expect(obtenerMatching).toHaveBeenCalledTimes(1)
  })

  it('descartar un renglón lo marca sin_presupuesto sin exigir confirmar los demás primero', async () => {
    vi.mocked(obtenerMatching).mockResolvedValue(matching())
    vi.mocked(descartarRenglon).mockResolvedValue(
      matching({
        renglones_oc: [
          renglonOc({ estado: 'sin_presupuesto', candidatos: [] }),
          renglonOc({
            oc_item_id: 'item-2',
            numero_renglon: 2,
            descripcion: 'Paracetamol 500mg x 10',
            precio_unitario: 500,
            candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }],
          }),
        ],
      }),
    )

    renderConQueryClient(<OcMatchingDetalle ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg x 20')
    fireEvent.click(screen.getAllByRole('button', { name: /no está en el presupuesto/i })[0])

    await waitFor(() => expect(descartarRenglon).toHaveBeenCalledWith('oc-1', 'item-1'))
    await waitFor(() =>
      expect(screen.getByText(/humano declaró que este renglón no está en el presupuesto/i)).toBeInTheDocument(),
    )
    // El segundo renglón sigue con su candidato disponible, sin bloquearse.
    expect(screen.getAllByRole('button', { name: /^confirmar$/i })).toHaveLength(1)
  })
})
