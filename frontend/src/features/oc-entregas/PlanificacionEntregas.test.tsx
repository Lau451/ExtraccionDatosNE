import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlanificacionEntregasOut, RenglonPlanificacion } from '@/lib/api/ocEntregas'
import { PlanificacionEntregas } from './PlanificacionEntregas'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/api/ocEntregas', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/ocEntregas')>('@/lib/api/ocEntregas')
  return {
    ...actual,
    obtenerPlanificacionEntregas: vi.fn(),
    planificarEntregas: vi.fn(),
  }
})

import { obtenerPlanificacionEntregas, planificarEntregas } from '@/lib/api/ocEntregas'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

function renglon(overrides: Partial<RenglonPlanificacion> = {}): RenglonPlanificacion {
  return {
    oc_item_id: 'item-1',
    numero_renglon: 1,
    numero_renglon_documento: null,
    descripcion: 'Ibuprofeno 400mg',
    cantidad: 100,
    producto_id: 'prod-1',
    producto_nombre: 'Ibuprofeno 400mg',
    unidades_por_presentacion: 25,
    ...overrides,
  }
}

function planificacion(overrides: Partial<PlanificacionEntregasOut> = {}): PlanificacionEntregasOut {
  return {
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-100',
    cantidad_entregas_sugerida: 3,
    renglones: [renglon()],
    pendientes: 0,
    descartados: 0,
    puede_planificar: true,
    motivo: null,
    plan_sugerido: [{ oc_item_id: 'item-1', cantidades: [50, 25, 25] }],
    plan_actual: [],
    ...overrides,
  }
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(obtenerPlanificacionEntregas).mockReset()
  vi.mocked(planificarEntregas).mockReset()
})

describe('PlanificacionEntregas (T4)', () => {
  it('precarga la grilla con plan_sugerido cuando no hay plan_actual', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue(50)
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue(25)
    expect(screen.getByLabelText('entrega 3 renglón 1')).toHaveValue(25)
  })

  it('precarga la grilla con plan_actual cuando ya existe un plan', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        plan_actual: [
          {
            numero_entrega: 1,
            fecha_entrega_planificada: null,
            estado: 'pendiente',
            items: [{ oc_item_id: 'item-1', cantidad_planificada: 40 }],
          },
          {
            numero_entrega: 2,
            fecha_entrega_planificada: null,
            estado: 'pendiente',
            items: [{ oc_item_id: 'item-1', cantidad_planificada: 60 }],
          },
        ],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByLabelText('cantidad de entregas')).toHaveValue(2)
    expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue(40)
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue(60)
  })

  it('cambiar N recalcula la sugerencia en el cliente, sin volver a pedirle nada al servidor', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.change(screen.getByLabelText('cantidad de entregas'), { target: { value: '2' } })

    await waitFor(() => expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue(50))
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue(50)
    expect(screen.queryByLabelText('entrega 3 renglón 1')).not.toBeInTheDocument()
    expect(obtenerPlanificacionEntregas).toHaveBeenCalledTimes(1)
  })

  it('una cantidad no múltiplo de la presentación muestra una advertencia no bloqueante con acción "usar"', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        plan_actual: [
          {
            numero_entrega: 1,
            fecha_entrega_planificada: null,
            estado: 'pendiente',
            items: [{ oc_item_id: 'item-1', cantidad_planificada: 30 }],
          },
          {
            numero_entrega: 2,
            fecha_entrega_planificada: null,
            estado: 'pendiente',
            items: [{ oc_item_id: 'item-1', cantidad_planificada: 25 }],
          },
        ],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByText(/no es múltiplo de 25/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /usar 25/i }))

    await waitFor(() => expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue(25))
  })

  it('deshabilita guardar mientras la suma de una fila no coincide con la cantidad del renglón', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByRole('button', { name: /guardar plan/i })).not.toBeDisabled()

    fireEvent.change(screen.getByLabelText('entrega 1 renglón 1'), { target: { value: '10' } })

    await waitFor(() => expect(screen.getByRole('button', { name: /guardar plan/i })).toBeDisabled())
  })

  it('guarda el plan y muestra las advertencias del servidor sin bloquear', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())
    vi.mocked(planificarEntregas).mockResolvedValue({
      orden_compra_id: 'oc-1',
      entregas: [],
      advertencias: [
        {
          oc_item_id: 'item-1',
          numero_entrega: 1,
          cantidad: 30,
          unidades_por_presentacion: 25,
          cantidad_sugerida: 25,
        },
      ],
    })

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.click(screen.getByRole('button', { name: /guardar plan/i }))

    await waitFor(() =>
      expect(planificarEntregas).toHaveBeenCalledWith('oc-1', [
        { numero_entrega: 1, fecha_entrega_planificada: null, items: [{ oc_item_id: 'item-1', cantidad: 50 }] },
        { numero_entrega: 2, fecha_entrega_planificada: null, items: [{ oc_item_id: 'item-1', cantidad: 25 }] },
        { numero_entrega: 3, fecha_entrega_planificada: null, items: [{ oc_item_id: 'item-1', cantidad: 25 }] },
      ]),
    )
    expect(await screen.findByText(/plan guardado/i)).toBeInTheDocument()
    expect(screen.getByText(/no es múltiplo de 25/i)).toBeInTheDocument()
  })

  it('un error del servidor al guardar se muestra de forma visible', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())
    vi.mocked(planificarEntregas).mockRejectedValue(
      new Error('Hay 1 renglón(es) pendiente(s) de matching -- resolvelos antes de planificar las entregas.'),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.click(screen.getByRole('button', { name: /guardar plan/i }))

    expect(await screen.findByText(/resolvelos antes de planificar/i)).toBeInTheDocument()
  })

  it('cuando puede_planificar es false muestra el motivo y un enlace de vuelta a matching, sin grilla', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        puede_planificar: false,
        motivo: 'Hay 1 renglón(es) pendiente(s) de matching -- resolvelos antes de planificar las entregas.',
        plan_sugerido: [],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText(/resolvelos antes de planificar/i)
    expect(screen.queryByLabelText('cantidad de entregas')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /volver al matching/i })).toBeInTheDocument()
  })

  it('con una entrega que ya no está pendiente muestra una vista de solo lectura del plan', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        puede_planificar: false,
        motivo: "El plan ya tiene una entrega que dejó de estar 'pendiente' -- no se puede replanificar.",
        plan_actual: [
          {
            numero_entrega: 1,
            fecha_entrega_planificada: null,
            estado: 'entregada',
            items: [{ oc_item_id: 'item-1', cantidad_planificada: 60 }],
          },
        ],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.queryByLabelText('cantidad de entregas')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /guardar plan/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /volver al matching/i })).toBeInTheDocument()
  })

  it('muestra un aviso con la cantidad de renglones descartados', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion({ descartados: 2 }))

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByText(/2 renglón\(es\) descartado/i)).toBeInTheDocument()
  })
})
