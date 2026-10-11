import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlanificacionEntregasOut, RenglonPlanificacion } from '@/lib/api/ocEntregas'
import { ApiError } from '@/lib/api/presupuestacion'
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

vi.mock('@/lib/api/ocExport', () => ({ exportarAProgress: vi.fn() }))

import { obtenerPlanificacionEntregas, planificarEntregas } from '@/lib/api/ocEntregas'
import { exportarAProgress } from '@/lib/api/ocExport'

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
  vi.mocked(exportarAProgress).mockReset()
})

describe('PlanificacionEntregas (T4)', () => {
  it('precarga la grilla con plan_sugerido cuando no hay plan_actual', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue('50')
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue('25')
    expect(screen.getByLabelText('entrega 3 renglón 1')).toHaveValue('25')
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
    expect(screen.getByLabelText('cantidad de entregas')).toHaveValue('2')
    expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue('40')
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue('60')
  })

  it('cambiar N recalcula la sugerencia en el cliente, sin volver a pedirle nada al servidor', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.change(screen.getByLabelText('cantidad de entregas'), { target: { value: '2' } })

    await waitFor(() => expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue('50'))
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue('50')
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

    await waitFor(() => expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue('25'))
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

  // Fix de review: si N supera la cantidad de packs, sugerirPlanRenglon puede
  // dejar una entrega entera en 0 (p.ej. 100 unidades x25, N=5 -> packs=4,
  // la 5ta entrega no tiene ningún pack para repartir). El backend rechaza
  // esa entrega con 422 ("no puede tener todas las cantidades en cero") --
  // esto lo bloquea antes, del lado del cliente.
  it('N excede los packs disponibles: bloquea Guardar y avisa qué entrega quedó vacía (100 x25, N=5)', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        renglones: [renglon({ cantidad: 100 })],
        plan_sugerido: [{ oc_item_id: 'item-1', cantidades: [25, 25, 25, 25] }],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.change(screen.getByLabelText('cantidad de entregas'), { target: { value: '5' } })

    await waitFor(() => expect(screen.getByLabelText('entrega 5 renglón 1')).toHaveValue('0'))
    expect(screen.getByText(/la entrega 5 no tiene cantidades/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar plan/i })).toBeDisabled()
  })

  it('una entrega vacía deja de bloquear en cuanto se le carga alguna cantidad', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        renglones: [renglon({ cantidad: 100 })],
        plan_sugerido: [{ oc_item_id: 'item-1', cantidades: [25, 25, 25, 25] }],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    fireEvent.change(screen.getByLabelText('cantidad de entregas'), { target: { value: '5' } })
    await waitFor(() => expect(screen.getByLabelText('entrega 5 renglón 1')).toHaveValue('0'))

    fireEvent.change(screen.getByLabelText('entrega 4 renglón 1'), { target: { value: '15' } })
    fireEvent.change(screen.getByLabelText('entrega 5 renglón 1'), { target: { value: '10' } })

    await waitFor(() =>
      expect(screen.queryByText(/la entrega 5 no tiene cantidades/i)).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /guardar plan/i })).not.toBeDisabled()
  })

  // Fix de review: la resta de floats para "restante" puede dejar residuo
  // binario (p.ej. 100 - 33.33 - 33.33 - 33.34 !== 0 por punto flotante) y
  // bloquear Guardar aunque la suma sea correcta -- se compara redondeado a
  // centavos (NUMERIC(12,2)).
  it('no bloquea Guardar por residuo binario cuando la suma coincide a centavos', async () => {
    // 0.1 + 0.2 === 0.30000000000000004 en punto flotante -- sin redondear,
    // `renglon.cantidad - suma` da un residuo != 0 y bloquearía Guardar
    // aunque la suma sea correcta a centavos (NUMERIC(12,2)).
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        cantidad_entregas_sugerida: 2,
        renglones: [renglon({ cantidad: 0.3, unidades_por_presentacion: null })],
        plan_sugerido: [{ oc_item_id: 'item-1', cantidades: [0.1, 0.2] }],
      }),
    )

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(screen.getByRole('button', { name: /guardar plan/i })).not.toBeDisabled()
  })

  it('al guardar con éxito invalida la query de planificación (refetch)', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())
    vi.mocked(planificarEntregas).mockResolvedValue({ orden_compra_id: 'oc-1', entregas: [], advertencias: [] })

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    expect(obtenerPlanificacionEntregas).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /guardar plan/i }))

    await waitFor(() => expect(screen.getByText(/plan guardado/i)).toBeInTheDocument())
    await waitFor(() => expect(obtenerPlanificacionEntregas).toHaveBeenCalledTimes(2))
  })
})

describe('PlanificacionEntregas — escribir los números directamente', () => {
  it('los campos son de texto con teclado numérico, sin flechitas de sumar o restar', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const cantidad = screen.getByLabelText('entrega 1 renglón 1')
    expect(cantidad).toHaveAttribute('type', 'text')
    expect(cantidad).toHaveAttribute('inputmode', 'decimal')
    const n = screen.getByLabelText('cantidad de entregas')
    expect(n).toHaveAttribute('type', 'text')
    expect(n).toHaveAttribute('inputmode', 'numeric')
  })

  it('una cantidad se puede borrar: el campo queda vacío y cuenta como 0', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const campo = screen.getByLabelText('entrega 1 renglón 1')
    fireEvent.change(campo, { target: { value: '' } })

    expect(campo).toHaveValue('')
    // 100 - (0 + 25 + 25)
    expect(screen.getByText('50')).toBeInTheDocument()
  })

  it('al hacer foco se selecciona todo el contenido para escribir encima', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const campo = screen.getByLabelText('entrega 1 renglón 1') as HTMLInputElement
    fireEvent.focus(campo)

    expect(campo.selectionStart).toBe(0)
    expect(campo.selectionEnd).toBe(campo.value.length)
  })

  it('ignora lo que no es un número', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const campo = screen.getByLabelText('entrega 1 renglón 1')
    fireEvent.change(campo, { target: { value: '5a' } })

    expect(campo).toHaveValue('50')
  })

  it('la cantidad de entregas se puede borrar y reescribir sin volver a 1', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const n = screen.getByLabelText('cantidad de entregas')
    fireEvent.change(n, { target: { value: '' } })

    expect(n).toHaveValue('')
    // Mientras está vacío no se tocan las columnas.
    expect(screen.getByLabelText('entrega 3 renglón 1')).toBeInTheDocument()

    fireEvent.change(n, { target: { value: '4' } })
    await waitFor(() => expect(screen.getByLabelText('entrega 4 renglón 1')).toBeInTheDocument())
  })

  it('si la cantidad de entregas queda vacía al salir del campo, vuelve al valor anterior', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const n = screen.getByLabelText('cantidad de entregas')
    fireEvent.change(n, { target: { value: '' } })
    fireEvent.blur(n)

    expect(n).toHaveValue('3')
  })

  it('fuera de rango: al salir del campo muestra el valor que realmente se aplicó', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const n = screen.getByLabelText('cantidad de entregas')
    fireEvent.change(n, { target: { value: '30' } })
    await waitFor(() => expect(n).toHaveValue('24'))

    // Ya en el máximo: 99 se recorta a 24, el valor no cambia.
    fireEvent.change(n, { target: { value: '99' } })
    fireEvent.blur(n)

    expect(n).toHaveValue('24')
  })

  it('cero cuando ya está en 1: al salir del campo vuelve a 1', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion({ cantidad_entregas_sugerida: 1 }))

    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    await screen.findByText('Ibuprofeno 400mg')
    const n = screen.getByLabelText('cantidad de entregas')
    fireEvent.change(n, { target: { value: '0' } })
    fireEvent.blur(n)

    expect(n).toHaveValue('1')
  })
})

describe('PlanificacionEntregas -- Exportar a Progress (D11)', () => {
  const planGuardado = [
    {
      numero_entrega: 1,
      fecha_entrega_planificada: '2026-11-01',
      estado: 'pendiente',
      items: [{ oc_item_id: 'item-1', cantidad_planificada: 100 }],
    },
  ]
  const exportacion = {
    exportado_at: '2026-10-11T12:00:00Z',
    exportado_por: '6f0d4f0e-0000-4000-8000-000000000001',
    exportado_por_nombre: 'Ana Pérez' as string | null,
    archivo_exportado: 'C001_OC-100_v1.csv',
  }
  const botonExportar = () => screen.getByRole('button', { name: 'Exportar a Progress' })

  async function renderConPlanGuardado() {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion({ plan_actual: planGuardado }))
    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)
    await screen.findByText('Ibuprofeno 400mg')
  }

  async function confirmarExportacion() {
    fireEvent.click(botonExportar())
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar' }))
  }

  it('el botón está habilitado con el plan guardado y sin exportar', async () => {
    await renderConPlanGuardado()
    expect(botonExportar()).toBeEnabled()
  })

  it('el botón está deshabilitado cuando todavía no hay plan guardado', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion())
    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)
    await screen.findByText('Ibuprofeno 400mg')
    expect(botonExportar()).toBeDisabled()
  })

  it('el botón se deshabilita con cambios sin guardar y avisa por qué', async () => {
    await renderConPlanGuardado()
    fireEvent.change(screen.getByLabelText('entrega 1 renglón 1'), { target: { value: '90' } })

    await waitFor(() => expect(botonExportar()).toBeDisabled())
    expect(screen.getByText(/Guardá el plan antes de exportar/)).toBeInTheDocument()
  })

  it('pide confirmación avisando que el plan no podrá modificarse y no exporta hasta confirmar', async () => {
    await renderConPlanGuardado()
    fireEvent.click(botonExportar())

    expect(await screen.findByText(/ya no (se )?podrá modificarse|no podrá modificarse/)).toBeInTheDocument()
    expect(exportarAProgress).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(exportarAProgress).not.toHaveBeenCalled()
  })

  it('al confirmar exporta y muestra el nombre del archivo generado', async () => {
    await renderConPlanGuardado()
    vi.mocked(exportarAProgress).mockResolvedValue({
      archivo: 'C001_OC-100_v1.csv',
      exportado_at: '2026-10-11T12:00:00Z',
      exportado_por: 'user-1',
      filas: 3,
    })
    await confirmarExportacion()

    expect(await screen.findByText(/C001_OC-100_v1\.csv/)).toBeInTheDocument()
    expect(exportarAProgress).toHaveBeenCalledWith('oc-1')
  })

  it('422: lista todas las precondiciones fallidas juntas', async () => {
    await renderConPlanGuardado()
    vi.mocked(exportarAProgress).mockRejectedValue(
      new ApiError(
        'No se puede exportar la orden de compra a Progress: el cliente no tiene CUIT; falta la fecha de emisión',
        422,
      ),
    )
    await confirmarExportacion()

    expect(await screen.findByText('el cliente no tiene CUIT')).toBeInTheDocument()
    expect(screen.getByText('falta la fecha de emisión')).toBeInTheDocument()
  })

  it('503: muestra que la integración no está configurada', async () => {
    await renderConPlanGuardado()
    vi.mocked(exportarAProgress).mockRejectedValue(
      new ApiError('La exportación a Progress no está configurada (falta PROGRESS_DOCS_DIR)', 503),
    )
    await confirmarExportacion()

    expect(await screen.findByText(/falta PROGRESS_DOCS_DIR/)).toBeInTheDocument()
  })

  it('409: muestra el mensaje y refresca la planificación (queda reflejado el estado exportado)', async () => {
    await renderConPlanGuardado()
    vi.mocked(exportarAProgress).mockRejectedValue(new ApiError('La orden de compra ya fue exportada', 409))
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({ plan_actual: planGuardado, puede_planificar: false, motivo: 'ya exportada', exportacion }),
    )
    await confirmarExportacion()

    expect(await screen.findByText(/Exportada a Progress el/)).toBeInTheDocument()
    expect(obtenerPlanificacionEntregas).toHaveBeenCalledTimes(2)
  })

  it('409 con plan cambiado (no exportada): la grilla se re-siembra con los datos frescos', async () => {
    await renderConPlanGuardado()
    expect(screen.getByLabelText('cantidad de entregas')).toHaveValue('1')
    vi.mocked(exportarAProgress).mockRejectedValue(new ApiError('El plan cambió durante la exportación', 409))
    const servidor = [
      { ...planGuardado[0], items: [{ oc_item_id: 'item-1', cantidad_planificada: 60 }] },
      { ...planGuardado[0], numero_entrega: 2, items: [{ oc_item_id: 'item-1', cantidad_planificada: 40 }] },
    ]
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(planificacion({ plan_actual: servidor }))
    await confirmarExportacion()

    expect(await screen.findByText('El plan cambió durante la exportación')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('cantidad de entregas')).toHaveValue('2'))
    expect(screen.getByLabelText('entrega 1 renglón 1')).toHaveValue('60')
    expect(screen.getByLabelText('entrega 2 renglón 1')).toHaveValue('40')
    expect(botonExportar()).toBeEnabled()
  })

  it('403: muestra el error del backend', async () => {
    await renderConPlanGuardado()
    vi.mocked(exportarAProgress).mockRejectedValue(new ApiError('No tenés permiso para esta acción', 403))
    await confirmarExportacion()

    expect(await screen.findByText('No tenés permiso para esta acción')).toBeInTheDocument()
  })

  it('con exportación y nombre null: el banner omite "por …" y nunca muestra el UUID', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        plan_actual: planGuardado,
        puede_planificar: false,
        motivo: 'ya exportada',
        exportacion: { ...exportacion, exportado_por_nombre: null },
      }),
    )
    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    const banner = await screen.findByText(/Exportada a Progress el/)
    expect(banner).not.toHaveTextContent(' por ')
    expect(banner).not.toHaveTextContent(exportacion.exportado_por)
  })

  it('con exportación: banner con fecha, usuario y archivo; sin botón ni grilla editable', async () => {
    vi.mocked(obtenerPlanificacionEntregas).mockResolvedValue(
      planificacion({
        plan_actual: planGuardado,
        puede_planificar: false,
        motivo: 'La orden de compra ya fue exportada a Progress -- no se puede replanificar.',
        exportacion,
      }),
    )
    renderConQueryClient(<PlanificacionEntregas ordenCompraId="oc-1" />)

    expect(await screen.findByText(/Exportada a Progress el/)).toHaveTextContent('Ana Pérez')
    expect(screen.getByText(/C001_OC-100_v1\.csv/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Exportar a Progress' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Guardar plan' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('entrega 1 renglón 1')).not.toBeInTheDocument()
    expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument()
  })
})
