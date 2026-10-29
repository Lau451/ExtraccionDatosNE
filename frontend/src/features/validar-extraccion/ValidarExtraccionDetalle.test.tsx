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

const { tercerosMock } = vi.hoisted(() => {
  const tercero = (id: string, razon_social: string, cuit: string, codigo_interno: string) => ({
    id,
    drogueria_id: 'drog-1',
    codigo_interno,
    razon_social,
    nombre_fantasia: null,
    cuit,
    email: null,
    telefono: null,
    sitio_web: null,
    notas: null,
    activo: true,
    tiene_rol_cliente: true,
    tiene_rol_proveedor: false,
  })
  return {
    tercerosMock: [
      tercero('cli-1', 'Hospital Sayago', '30-11111111-1', 'C273'),
      tercero('cli-2', 'Clínica Norte', '30-22222222-2', 'C100'),
    ],
  }
})

// presupuestador-v1 T2b: the cliente is picked with ClienteBuscador
// (GET /terceros by razón social, CUIT or código). The fake filters by `q`.
vi.mock('@/lib/api/terceros', () => ({
  listarTerceros: vi.fn(async ({ q }: { q: string }) => ({
    items: tercerosMock.filter((tercero) =>
      [tercero.razon_social, tercero.cuit, tercero.codigo_interno].some((campo) =>
        campo.toLowerCase().includes(q.toLowerCase()),
      ),
    ),
    total: 0,
    page: 1,
    page_size: 20,
  })),
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
      cabecera: {
        numero_oc: string
        fecha_emision: string
        direccion_entrega: string
        observaciones: string
        cantidad_entregas: string
      },
      bloqueado: boolean,
    ) => void
  }) => {
    // Espeja el default real de CabeceraOrdenCompra: reporta su cabecera
    // (precargada, sin desacuerdo) apenas se monta, vía un useEffect --
    // igual que el componente real (design.md/CabeceraOrdenCompra.tsx).
    useEffect(() => {
      onCambio(
        {
          numero_oc: 'OC-4471',
          fecha_emision: '12/09/2026',
          direccion_entrega: 'Av. Siempreviva 742',
          observaciones: '',
          cantidad_entregas: '1',
        },
        false,
      )
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    return (
      <div>
        <p>cabecera-orden-compra-stub</p>
        <button
          type="button"
          onClick={() =>
            onCambio(
              {
                numero_oc: '',
                fecha_emision: '',
                direccion_entrega: '',
                observaciones: '',
                cantidad_entregas: '',
              },
              true,
            )
          }
        >
          stub-cabecera-bloqueada
        </button>
        <button
          type="button"
          onClick={() =>
            onCambio(
              {
                numero_oc: 'OC-4471',
                fecha_emision: '12/09/2026',
                direccion_entrega: 'Av. Siempreviva 742',
                observaciones: '  Entrega parcial  ',
                cantidad_entregas: '1',
              },
              false,
            )
          }
        >
          stub-observaciones
        </button>
        <button
          type="button"
          onClick={() =>
            onCambio(
              {
                numero_oc: 'OC-4471',
                fecha_emision: '12/09/2026',
                direccion_entrega: 'Av. Siempreviva 742',
                observaciones: '',
                cantidad_entregas: '3',
              },
              false,
            )
          }
        >
          stub-cantidad-entregas
        </button>
      </div>
    )
  },
}))

import { obtenerFilasExtraccion, validarExtraccion } from '@/lib/api/extracciones'
import { listarProcesosComerciales } from '@/lib/api/procesosComerciales'
import { listarTerceros } from '@/lib/api/terceros'

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
      notas: null, // T2: sin observaciones cargadas (stub default '') -> null, no ''
      cantidad_entregas: '1', // oc-entregas-planificacion T2: default del stub al montar
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
    // importe_total es control de UI (T2) -- nunca viaja en el override
    // (FilaOrdenCompraIn tiene extra="forbid" en el backend).
    expect(payload.orden_compra?.filas[0]).not.toHaveProperty('importe_total')
  })

  it('notas viaja con el valor trimeado de cabecera.observaciones cuando no está vacío (T2)', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    fireEvent.click(screen.getByText('stub-observaciones'))
    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )

    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    const [, payload] = vi.mocked(validarExtraccion).mock.calls[0]
    expect(payload.orden_compra?.notas).toBe('Entrega parcial')
  })

  it('cantidad_entregas viaja con el valor reportado por la cabecera (oc-entregas-planificacion T2)', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    fireEvent.click(screen.getByText('stub-cantidad-entregas'))
    await confirmarCliente()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^confirmar validación$/i })).not.toBeDisabled(),
    )

    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    const [, payload] = vi.mocked(validarExtraccion).mock.calls[0]
    expect(payload.orden_compra?.cantidad_entregas).toBe('3')
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

// T2 (extraccion-duplicado-link) — al abrir una extracción ya validada (desde
// el link del 409 duplicado, o navegación directa a la URL) la pantalla debe
// avisar en vez de ofrecer una segunda confirmación que el backend rechaza
// igual (ck_oc_extraction_unica). GET .../filas expone validado/orden_compra_id
// (backend, T2); acá se cablea la UI que reacciona a esos dos campos.
describe('ValidarExtraccionDetalle — extracción ya validada (T2)', () => {
  it('validado=true con orden_compra_id: aviso + botón "Ir a la orden de compra", sin selector/cabecera/tabla/confirmar', async () => {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'orden_compra',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: Object.keys(FILA_OC()),
      filas: [FILA_OC()],
      grupo_id: null,
      miembros: [],
      advertencias_cabecera: [],
      validado: true,
      orden_compra_id: 'oc-777',
    })

    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    expect(await screen.findByText(/esta extracción ya fue validada/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /ir a la orden de compra/i }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/ordenes-compra/$ordenCompraId/matching',
      params: { ordenCompraId: 'oc-777' },
    })

    expect(screen.queryByRole('button', { name: /^confirmar validación$/i })).not.toBeInTheDocument()
    expect(screen.queryByText('orden-compra-selector-stub')).not.toBeInTheDocument()
    expect(screen.queryByText('cabecera-orden-compra-stub')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /agregar fila/i })).not.toBeInTheDocument()
  })

  it('validado=true de una licitación: aviso + botón "Ir al matching" de su proceso (presupuestador-v1 T3)', async () => {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'licitacion',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['item', 'descripcion', 'cantidad'],
      filas: [{ item: '1', descripcion: 'Test', cantidad: '1' }],
      validado: true,
      orden_compra_id: null,
      proceso_comercial_id: 'proc-9',
    })

    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    expect(await screen.findByText(/esta extracción ya fue validada/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ir a la orden de compra/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^confirmar validación$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ir al matching' }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/procesos-comerciales/$procesoId/matching',
      params: { procesoId: 'proc-9' },
    })
  })

  it('validado=true de una comparativa: solo el aviso, sin botón', async () => {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'comparativa',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['renglon', 'proveedor', 'precio'],
      filas: [{ renglon: '1', proveedor: 'Proveedor A', precio: '10.00' }],
      validado: true,
      orden_compra_id: null,
      proceso_comercial_id: 'proc-9',
    })

    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    expect(await screen.findByText(/esta extracción ya fue validada/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ir a la orden de compra/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ir al matching' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^confirmar validación$/i })).not.toBeInTheDocument()
  })

  it('validado=false (u omitido, retrocompat) sigue mostrando el flujo normal de edición, sin el aviso', async () => {
    mockFilasOrdenCompra([FILA_OC()])
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    await screen.findByText('cabecera-orden-compra-stub')
    expect(screen.queryByText(/esta extracción ya fue validada/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^confirmar validación$/i })).toBeInTheDocument()
  })
})

// presupuestador-v1 T2b (S2, S8) -- validating a licitación or a directa starts
// its proceso comercial: class, cliente and (licitación) name are chosen here.
describe('ValidarExtraccionDetalle — licitación/directa crea su proceso (presupuestador-v1 T2b)', () => {
  function mockFilasLicitacion() {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'licitacion',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['item', 'cantidad', 'descripcion'],
      filas: [{ item: '1', cantidad: '180', descripcion: 'Alcohol etílico 96° x 500 ml' }],
    })
  }

  function botonConfirmar() {
    return screen.getByRole('button', { name: /^confirmar validación$/i })
  }

  async function elegirCliente(busqueda: string, nombre: string) {
    fireEvent.change(screen.getByPlaceholderText('Buscá por razón social, CUIT o código'), {
      target: { value: busqueda },
    })
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${nombre}`) }))
  }

  it('pide tipo, cliente y nombre en vez de un proceso existente, sin nada preseleccionado', async () => {
    mockFilasLicitacion()
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    expect(await screen.findByRole('button', { name: 'Licitación' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Directa' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByPlaceholderText('Buscá por razón social, CUIT o código')).toHaveValue('')
    expect(screen.queryByText('Proceso comercial')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Nombre de la licitación' })).not.toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()
    expect(screen.getByText('Elegí si es una licitación o una directa')).toBeInTheDocument()
  })

  it('explica qué falta hasta poder confirmar una licitación', async () => {
    mockFilasLicitacion()
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Licitación' }))
    expect(screen.getByText('Elegí el cliente')).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()

    await elegirCliente('Sayago', 'Hospital Sayago')
    expect(screen.getByText('Escribí el nombre de la licitación')).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox', { name: 'Nombre de la licitación' }), {
      target: { value: '   ' },
    })
    expect(screen.getByText('Escribí el nombre de la licitación')).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()
  })

  it('licitación: muestra el nombre del proceso y lo crea al confirmar', async () => {
    mockFilasLicitacion()
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Licitación' }))
    await elegirCliente('C273', 'Hospital Sayago')
    fireEvent.change(screen.getByRole('textbox', { name: 'Nombre de la licitación' }), {
      target: { value: '  lic 14/2026 ' },
    })

    expect(screen.getByRole('textbox', { name: 'Nombre de la licitación' })).toHaveValue('  LIC 14/2026 ')
    expect(screen.getByText('Se va a crear el proceso: Hospital Sayago - LIC 14/2026')).toBeInTheDocument()
    expect(screen.queryByText(/^Elegí|^Escribí/)).not.toBeInTheDocument()
    expect(botonConfirmar()).toBeEnabled()
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    expect(vi.mocked(validarExtraccion).mock.calls[0]).toEqual([
      'abc',
      {
        nuevo_proceso: {
          clase: 'licitacion',
          cliente_id: 'cli-1',
          nombre_licitacion: 'LIC 14/2026',
        },
        filas: [{ item: '1', cantidad: '180', descripcion: 'Alcohol etílico 96° x 500 ml' }],
      },
    ])
  })

  it('directa: no pide nombre, se numera sola y se crea al confirmar', async () => {
    mockFilasLicitacion()
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Directa' }))
    expect(screen.getByRole('button', { name: 'Directa' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByRole('textbox', { name: 'Nombre de la licitación' })).not.toBeInTheDocument()
    expect(screen.getByText('Elegí el cliente')).toBeInTheDocument()
    await elegirCliente('30-22222222', 'Clínica Norte')

    expect(
      screen.getByText('Se va a crear el proceso: Clínica Norte - (número siguiente de directa)'),
    ).toBeInTheDocument()
    expect(botonConfirmar()).toBeEnabled()
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    expect(vi.mocked(validarExtraccion).mock.calls[0][1]).toEqual({
      nuevo_proceso: { clase: 'cotizacion', cliente_id: 'cli-2' },
      filas: [{ item: '1', cantidad: '180', descripcion: 'Alcohol etílico 96° x 500 ml' }],
    })
  })

  it('la comparativa sigue eligiendo un proceso existente y dice qué falta', async () => {
    vi.mocked(listarProcesosComerciales).mockResolvedValue([
      { id: 'proc-1', nombre: 'Hospital Sayago - LIC 14/2026', clase: 'licitacion', estado: 'abierto' },
    ])
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'comparativa',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['renglon', 'proveedor', 'precio'],
      filas: [{ renglon: '1', proveedor: 'Proveedor A', precio: '10.00' }],
    })
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    expect(await screen.findByText('Proceso comercial')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Licitación' })).not.toBeInTheDocument()
    expect(screen.getByText('Elegí el proceso comercial')).toBeInTheDocument()
    expect(botonConfirmar()).toBeDisabled()

    const selector = screen.getAllByRole('combobox')[0]
    await within(selector).findByRole('option', { name: 'Hospital Sayago - LIC 14/2026' })
    fireEvent.change(selector, { target: { value: 'proc-1' } })
    expect(screen.queryByText('Elegí el proceso comercial')).not.toBeInTheDocument()
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(validarExtraccion).toHaveBeenCalledTimes(1))
    expect(vi.mocked(validarExtraccion).mock.calls[0][1]).toEqual({
      proceso_comercial_id: 'proc-1',
      filas: [{ renglon: '1', proveedor: 'Proveedor A', marca: '', precio: '10.00' }],
    })
  })

  function resultadoValidacion(documentType: 'licitacion' | 'cotizacion' | 'comparativa') {
    return {
      extraction_id: 'abc',
      document_type: documentType,
      proceso_comercial_id: 'proc-9',
      filas_creadas: 1,
      comparativa_id: documentType === 'comparativa' ? 'comp-1' : null,
      reemplazo_version_anterior: false,
      orden_compra_id: null,
      entregas_creadas: 0,
      renglones_sin_producto: 0,
      extracciones_validadas: 1,
    }
  }

  it.each(['licitacion', 'cotizacion'] as const)(
    '%s: al confirmar abre el matching del proceso creado (presupuestador-v1 T3c)',
    async (documentType) => {
      mockFilasLicitacion()
      vi.mocked(validarExtraccion).mockResolvedValueOnce(resultadoValidacion(documentType))
      renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

      fireEvent.click(await screen.findByRole('button', { name: 'Directa' }))
      await elegirCliente('30-22222222', 'Clínica Norte')
      await abrirYConfirmarDialogo()

      await waitFor(() =>
        expect(navigateMock).toHaveBeenCalledWith({
          to: '/procesos-comerciales/$procesoId/matching',
          params: { procesoId: 'proc-9' },
        }),
      )
      expect(navigateMock).not.toHaveBeenCalledWith({ to: '/validar-extraccion' })
    },
  )

  it('la comparativa sigue volviendo al listado al confirmar', async () => {
    vi.mocked(listarProcesosComerciales).mockResolvedValue([
      { id: 'proc-9', nombre: 'Hospital Sayago - LIC 14/2026', clase: 'licitacion', estado: 'abierto' },
    ])
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'comparativa',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['renglon', 'proveedor', 'precio'],
      filas: [{ renglon: '1', proveedor: 'Proveedor A', precio: '10.00' }],
    })
    vi.mocked(validarExtraccion).mockResolvedValueOnce(resultadoValidacion('comparativa'))
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)

    const selector = (await screen.findAllByRole('combobox'))[0]
    await within(selector).findByRole('option', { name: 'Hospital Sayago - LIC 14/2026' })
    fireEvent.change(selector, { target: { value: 'proc-9' } })
    await abrirYConfirmarDialogo()

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: '/validar-extraccion' }))
    expect(navigateMock).toHaveBeenCalledTimes(1)
  })
})

describe('ValidarExtraccionDetalle — buscador de cliente (presupuestador-v1 T2b)', () => {
  beforeEach(() => {
    vi.mocked(obtenerFilasExtraccion).mockResolvedValue({
      extraction_id: 'abc',
      document_type: 'licitacion',
      row_count: 1,
      filas_leidas: 1,
      editable: true,
      columnas: ['item', 'cantidad', 'descripcion'],
      filas: [{ item: '1', cantidad: '180', descripcion: 'Alcohol etílico 96° x 500 ml' }],
    })
  })

  it.each([
    ['código', 'C273'],
    ['CUIT', '30-11111111'],
    ['razón social', 'sayago'],
  ])('busca el cliente por %s', async (_campo, busqueda) => {
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Directa' }))

    fireEvent.change(screen.getByPlaceholderText('Buscá por razón social, CUIT o código'), {
      target: { value: busqueda },
    })

    expect(
      await screen.findByRole('button', { name: /^Hospital Sayago.*CUIT 30-11111111-1 · C273$/ }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Clínica Norte/ })).not.toBeInTheDocument()
    expect(vi.mocked(listarTerceros)).toHaveBeenLastCalledWith({ q: busqueda, rol: 'todos', pageSize: 20 })
  })

  it('muestra el cliente elegido y permite cambiarlo', async () => {
    renderConQueryClient(<ValidarExtraccionDetalle extractionId="abc" rowCountHint={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Directa' }))
    fireEvent.change(screen.getByPlaceholderText('Buscá por razón social, CUIT o código'), {
      target: { value: 'C273' },
    })
    fireEvent.click(await screen.findByRole('button', { name: /^Hospital Sayago/ }))

    expect(screen.getByText('Hospital Sayago · CUIT 30-11111111-1 · C273')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Buscá por razón social, CUIT o código')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^confirmar validación$/i })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Cambiar cliente' }))

    expect(screen.getByPlaceholderText('Buscá por razón social, CUIT o código')).toHaveValue('')
    expect(screen.getByText('Elegí el cliente')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^confirmar validación$/i })).toBeDisabled()
  })
})
