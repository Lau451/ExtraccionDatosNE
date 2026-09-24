import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ValidarExtraccionDetalle } from './ValidarExtraccionDetalle'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
}))

vi.mock('@/lib/api/extracciones', () => ({
  obtenerFilasExtraccion: vi.fn(),
  validarExtraccion: vi.fn(),
}))

vi.mock('@/lib/api/procesosComerciales', () => ({
  listarProcesosComerciales: vi.fn().mockResolvedValue([]),
  crearProcesoComercial: vi.fn(),
}))

// Los 3 componentes de Phases 6/7 ya tienen su propio contrato probado
// (OrdenCompraSelector.test.tsx, CabeceraOrdenCompra.test.tsx,
// EntregasEditor.test.tsx). Acá se reemplazan por stubs mínimos que exponen
// SOLO el contrato de callback ya establecido (onClienteConfirmado /
// onCambio) -- Phase 8 prueba el WIRING, no vuelve a probar cada componente.
vi.mock('./components/OrdenCompraSelector', () => ({
  OrdenCompraSelector: ({
    onClienteConfirmado,
  }: {
    onClienteConfirmado: (clienteId: string, razonSocialExtraida: string | null) => void
  }) => (
    <div>
      <p>orden-compra-selector-stub</p>
      <button type="button" onClick={() => onClienteConfirmado('cli-1', 'HOSPITAL CENTRAL')}>
        stub-confirmar-cliente
      </button>
    </div>
  ),
}))

vi.mock('./components/CabeceraOrdenCompra', () => ({
  CabeceraOrdenCompra: ({
    onCambio,
  }: {
    onCambio: (
      cabecera: { numero_oc: string; fecha_emision: string; direccion_entrega: string },
      bloqueado: boolean,
    ) => void
  }) => {
    // Espeja el default real de CabeceraOrdenCompra: reporta su cabecera
    // (precargada, sin desacuerdo) apenas se monta, vía un useEffect --
    // igual que el componente real (design.md/CabeceraOrdenCompra.tsx).
    useEffect(() => {
      onCambio(
        { numero_oc: 'OC-4471', fecha_emision: '12/09/2026', direccion_entrega: 'Av. Siempreviva 742' },
        false,
      )
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    return (
      <div>
        <p>cabecera-orden-compra-stub</p>
        <button
          type="button"
          onClick={() => onCambio({ numero_oc: '', fecha_emision: '', direccion_entrega: '' }, true)}
        >
          stub-cabecera-bloqueada
        </button>
      </div>
    )
  },
}))

import { obtenerFilasExtraccion, validarExtraccion } from '@/lib/api/extracciones'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

const FILA_OC = (overrides: Record<string, string> = {}) => ({
  numero_oc: 'OC-4471',
  fecha_emision: '12/09/2026',
  cuit_cliente: '30712345679',
  razon_social_cliente: 'HOSPITAL SAN ROQUE',
  direccion_entrega: 'Av. Siempreviva 742',
  cantidad_entregas: '1',
  numero_renglon: '1',
  descripcion: 'Ibuprofeno 400mg x 20',
  cantidad: '100',
  precio_unitario: '1250,00',
  entregas: '',
  _archivo: 'oc-hospital.pdf',
  _extraction_id: 'ext-1',
  ...overrides,
})

function mockFilasOrdenCompra(filas: ReturnType<typeof FILA_OC>[]) {
  vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
    extraction_id: 'abc',
    document_type: 'orden_compra',
    row_count: filas.length,
    filas_leidas: filas.length,
    editable: true,
    columnas: Object.keys(filas[0] ?? {}),
    filas,
    grupo_id: null,
    miembros: [],
    advertencias_cabecera: [],
  })
}

async function confirmarCliente() {
  fireEvent.click(await screen.findByText('stub-confirmar-cliente'))
}

async function abrirYConfirmarDialogo() {
  fireEvent.click(screen.getByRole('button', { name: /^confirmar validación$/i }))
  const dialog = await screen.findByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: /^confirmar validación$/i }))
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(obtenerFilasExtraccion).mockReset()
  vi.mocked(validarExtraccion).mockReset()
  vi.mocked(validarExtraccion).mockResolvedValue({
    extraction_id: 'abc',
    document_type: 'orden_compra',
    proceso_comercial_id: null,
    filas_creadas: 1,
    comparativa_id: null,
    reemplazo_version_anterior: false,
    // D10/D13 (Phase 6) -- los 4 campos que el backend ya devuelve desde
    // 3b37fca3 (C7); el default de esta suite espeja el default real del
    // backend (orden_compra_id null -> navega al listado, ver describe
    // "navegación tras confirmar" más abajo).
    orden_compra_id: null,
    entregas_creadas: 0,
    renglones_sin_producto: 0,
    extracciones_validadas: 1,
  })
})

describe('ValidarExtraccionDetalle — gate de tamaño (D7)', () => {
  it('row_count > 500 (por el hint del listado) no dispara la query de /filas y renderiza el estado bloqueado', async () => {
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={812} />)

    await waitFor(() =>
      expect(screen.getByText(/documento demasiado grande/i)).toBeInTheDocument(),
    )
    expect(obtenerFilasExtraccion).not.toHaveBeenCalled()
    expect(screen.getByText(/812/)).toBeInTheDocument()
  })

  it('row_count <= 500 sí dispara la query de /filas', async () => {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'licitacion',
      row_count: 2,
      filas_leidas: 2,
      editable: true,
      columnas: ['item', 'descripcion', 'cantidad'],
      filas: [{ item: '1', descripcion: 'Test', cantidad: '1' }],
    })

    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={2} />)

    await waitFor(() => expect(obtenerFilasExtraccion).toHaveBeenCalledWith('abc'))
    expect(screen.queryByText(/documento demasiado grande/i)).not.toBeInTheDocument()
  })
})

// Phase 8 (D7/D13/D13.1) — wiring final: rama document_type === 'orden_compra'.
describe('ValidarExtraccionDetalle — rama orden_compra (Phase 8)', () => {
  it('no renderiza ProcesoComercialSelector ni EntregasEditor; renderiza CabeceraOrdenCompra + OrdenCompraSelector', async () => {
    // Ajuste post-shipping (2026-09-21): la división en entregas se saca del
    // flujo de confirmación de OC -- EntregasEditor ya NO se renderiza acá
    // (se mueve a una fase futura de matching, todavía sin diseñar). El
    // componente y sus tests propios (EntregasEditor.test.tsx) se conservan
    // sin tocar, solo se deja de invocar desde esta pantalla.
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    expect(screen.getByText('orden-compra-selector-stub')).toBeInTheDocument()
    // EntregasEditor.tsx ya NO está mockeado en este archivo (se sacó el
    // vi.mock) -- si el componente real se siguiera renderizando acá, su
    // label "Cantidad de entregas" aparecería en el DOM.
    expect(screen.queryByText(/cantidad de entregas/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/proceso comercial/i)).not.toBeInTheDocument()
  })

  it('onBorrarFila/onAgregarFila siguen cableadas igual que hoy: agregar fila suma una fila vacía a la tabla', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    expect(screen.getAllByRole('textbox', { name: /^descripción fila/i })).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: /agregar fila/i }))

    expect(screen.getAllByRole('textbox', { name: /^descripción fila/i })).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: /^borrar fila 1$/i }))
    expect(screen.getByRole('button', { name: /^deshacer borrado de fila 1$/i })).toBeInTheDocument()
  })

  it('puedeConfirmar exige cliente_id confirmado + cabecera sin bloqueos (ya no depende de entregas)', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    const botonConfirmar = screen.getByRole('button', { name: /^confirmar validación$/i })

    // Cabecera ya se auto-reportó sin bloqueo al montar (mismo comportamiento
    // del componente real) -- solo falta el cliente.
    expect(botonConfirmar).toBeDisabled()

    await confirmarCliente()
    // Las 2 condiciones están cumplidas: cliente confirmado, cabecera sin
    // bloqueos -- ya no hay una tercera condición de entregas.
    await waitFor(() => expect(botonConfirmar).not.toBeDisabled())

    // Si la cabecera pasa a bloqueada (p. ej. numero_oc en desacuerdo sin
    // resolver), puedeConfirmar vuelve a false.
    fireEvent.click(screen.getByText('stub-cabecera-bloqueada'))
    expect(botonConfirmar).toBeDisabled()
  })

  it('el payload enviado a validarExtraccion lleva orden_compra (fecha ISO, cliente, filas) sin entregas ni filas', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )

    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    const [extractionId, payload] = vi.mocked(validarExtraccion).mock.calls[0]
    expect(extractionId).toBe('abc')
    expect(payload.filas).toBeUndefined()
    expect(payload.orden_compra).toMatchObject({
      numero_oc: 'OC-4471',
      cliente_id: 'cli-1',
      razon_social_extraida: 'HOSPITAL CENTRAL',
      fecha_emision: '2026-09-12', // D6: DD/MM/AAAA en el documento -> ISO para el backend
      direccion_entrega: 'Av. Siempreviva 742',
    })
    expect(payload.orden_compra).not.toHaveProperty('entregas')
    expect(payload.orden_compra?.filas).toEqual([
      {
        numero_renglon_documento: '1',
        descripcion: 'Ibuprofeno 400mg x 20',
        cantidad: '100',
        precio_unitario: '1250,00',
        producto_id: null,
      },
    ])
  })
})

// Phase 6 (D10) — navegación automática al confirmar, según `orden_compra_id`
// del resultado. La rama de `onSuccess` decide únicamente por ese campo, no
// por `document_type` (design.md D10): por eso ambos casos se ejercitan sobre
// el mismo flujo ya estable de `orden_compra` (stubs de OrdenCompraSelector/
// CabeceraOrdenCompra ya establecidos arriba), variando solo el
// `orden_compra_id` que la mutación resuelve. Nota de rigor: no existía
// ningún test previo en este archivo que afirmara la navegación al listado
// (`navigateMock` estaba declarado pero nunca aserteado) -- confirmado con
// `rg navigateMock` antes de escribir este bloque -- así que "extender" el
// caso null es, en los hechos, el primer test de navegación de este archivo,
// no una extensión literal de uno preexistente.
describe('ValidarExtraccionDetalle — navegación tras confirmar (D10)', () => {
  it('confirmar una orden de compra con orden_compra_id navega a la pantalla de matching', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    vi.mocked(validarExtraccion).mockResolvedValueOnce({
      extraction_id: 'abc',
      document_type: 'orden_compra',
      proceso_comercial_id: null,
      filas_creadas: 1,
      comparativa_id: null,
      reemplazo_version_anterior: false,
      orden_compra_id: 'oc-999',
      entregas_creadas: 0,
      renglones_sin_producto: 0,
      extracciones_validadas: 1,
    })
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )
    await abrirYConfirmarDialogo()

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith({
        to: '/ordenes-compra/$ordenCompraId/matching',
        params: { ordenCompraId: 'oc-999' },
      }),
    )
    expect(navigateMock).not.toHaveBeenCalledWith({ to: '/validar-extraccion' })
  })

  it('confirmar una extracción cuyo resultado trae orden_compra_id null (licitación/comparativa) sigue navegando al listado', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    vi.mocked(validarExtraccion).mockResolvedValueOnce({
      extraction_id: 'abc',
      document_type: 'orden_compra',
      proceso_comercial_id: null,
      filas_creadas: 1,
      comparativa_id: null,
      reemplazo_version_anterior: false,
      orden_compra_id: null,
      entregas_creadas: 0,
      renglones_sin_producto: 0,
      extracciones_validadas: 1,
    })
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: '/validar-extraccion' }))
    expect(navigateMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ to: '/ordenes-compra/$ordenCompraId/matching' }),
    )
  })
})

// Phase 8 / task 8.3 (D13.1) — reconciliación manual explícita de un grupo.
describe('ValidarExtraccionDetalle — reconciliación manual de grupo (D13.1, task 8.3)', () => {
  const GRUPO_3_MIEMBROS = [
    FILA_OC({ numero_renglon: '1', descripcion: 'Renglón A', _extraction_id: 'ext-1', _archivo: 'a.pdf' }),
    FILA_OC({ numero_renglon: '1', descripcion: 'Renglón B (duplicado)', _extraction_id: 'ext-2', _archivo: 'b.pdf' }),
    FILA_OC({ numero_renglon: '1', descripcion: 'Renglón C', _extraction_id: 'ext-3', _archivo: 'c.pdf' }),
  ]

  it('la tabla muestra la concatenación de las 3 filas del grupo, sin fusionar ni deduplicar', async () => {
    mockFilasOrdenCompra(GRUPO_3_MIEMBROS)
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={3} />)

    await screen.findByText('cabecera-orden-compra-stub')
    expect(screen.getAllByRole('textbox', { name: /^descripción fila/i })).toHaveLength(3)
  })

  it('borrarFila sobre la fila duplicada la saca del payload enviado (queda solo A y C)', async () => {
    mockFilasOrdenCompra(GRUPO_3_MIEMBROS)
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={3} />)

    await screen.findByText('cabecera-orden-compra-stub')
    fireEvent.click(screen.getByRole('button', { name: /^borrar fila 2$/i }))

    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    const [, payload] = vi.mocked(validarExtraccion).mock.calls[0]
    expect(payload.orden_compra?.filas).toHaveLength(2)
    expect(payload.orden_compra?.filas.map((f) => f.descripcion)).toEqual(['Renglón A', 'Renglón C'])
  })

  it('no existe ningún selector de modo de fusión en la pantalla', async () => {
    mockFilasOrdenCompra(GRUPO_3_MIEMBROS)
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={3} />)

    await screen.findByText('cabecera-orden-compra-stub')
    expect(screen.queryByText(/modo de fusi/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /fusi/i })).not.toBeInTheDocument()
  })
})
