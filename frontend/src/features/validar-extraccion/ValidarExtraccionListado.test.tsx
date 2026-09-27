import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ValidarExtraccionListado, puedeAgruparSeleccion, grupoIdDe } from './ValidarExtraccionListado'
import type { ExtraccionResumen, ListarExtraccionesParams } from '@/lib/api/extracciones'

// D11 -- a diferencia del mock mínimo previo (`<a>{children}</a>`), esta
// versión propaga `to`/`params` como `href` para poder afirmar el destino
// real de los links de re-entrada (task 8.1). Sustituye literales de ruta
// tipo `$ordenCompraId` por el valor correspondiente en `params`, mismo
// criterio que `LoginForm.test.tsx` (único precedente que ya exponía `to`).
vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children?: React.ReactNode
    to: string
    params?: Record<string, string>
  }) => {
    let href = to
    if (params) {
      for (const [clave, valor] of Object.entries(params)) href = href.replace(`$${clave}`, valor)
    }
    return <a href={href}>{children}</a>
  },
}))

vi.mock('@/lib/api/extracciones', () => ({
  listarExtracciones: vi.fn(),
  agruparExtracciones: vi.fn(),
  desagruparExtracciones: vi.fn(),
}))

import { agruparExtracciones, desagruparExtracciones, listarExtracciones } from '@/lib/api/extracciones'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

// T2 (validar-extraccion-organizacion) -- GET /extracciones ya no se separa
// por validado=true/false (T1): un único query devuelve las 4 status y ambos
// valores de `validado`. La fábrica de fixtures/mocks se actualiza para ese
// contrato -- ver ExtraccionResumen (lib/api/extracciones.ts).
const OC_1: ExtraccionResumen = {
  id: 'ex-1',
  document_type: 'orden_compra',
  source_filename: 'oc1.pdf',
  row_count: 2,
  status: 'completed',
  error_msg: null,
  validado: false,
  proceso_comercial_id: null,
  proceso_comercial_nombre: null,
  created_at: '2026-01-01T00:00:00Z',
  orden_compra_id: null,
  subido_por: 'user-1',
  subido_por_nombre: 'Ana Gómez',
}
const OC_2: ExtraccionResumen = { ...OC_1, id: 'ex-2', source_filename: 'oc2.pdf' }
const LICITACION_1: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-3',
  document_type: 'licitacion',
  source_filename: 'lici1.pdf',
}

// D11 (Phase 8, tasks 8.1-8.2) -- una OC validada, con `orden_compra_id`
// resuelto (ancla del grupo, o sin grupo). Base para el fixture "sin ancla"
// (orden_compra_id: null) de cada test que lo necesita.
const OC_VALIDADA_1: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-validada-1',
  source_filename: 'oc-validada-1.pdf',
  validado: true,
  orden_compra_id: 'oc-abc',
}

const PROCESANDO_1: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-procesando-1',
  source_filename: 'oc-procesando.pdf',
  status: 'processing',
}

const ERROR_1: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-error-1',
  source_filename: 'oc-error.pdf',
  status: 'failed',
  error_msg: 'El documento no tiene un formato reconocido.',
}

const SIN_UPLOADER: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-sin-uploader',
  source_filename: 'oc-sin-uploader.pdf',
  subido_por: null,
  subido_por_nombre: null,
}

/** T2 (corrección) -- el componente vuelve a llamar `listarExtracciones` dos
 * veces (pendientes `validado:false` + validadas `validado:true`), como el
 * backend real. La fábrica toma UN array con el fixture completo (mezclando
 * filas validadas y sin validar, como antes de la corrección) y lo separa
 * por `extraccion.validado` según qué rama pida cada llamada -- así los
 * tests existentes que ya arman fixtures con ambas clases de fila no
 * necesitan reescribirse. */
function mockListarExtracciones(extracciones: ExtraccionResumen[] = [OC_1, OC_2, LICITACION_1]) {
  vi.mocked(listarExtracciones)
    .mockReset()
    .mockImplementation((params: ListarExtraccionesParams = {}) => {
      if (params.validado === false) return Promise.resolve(extracciones.filter((e) => !e.validado))
      if (params.validado === true) return Promise.resolve(extracciones.filter((e) => e.validado))
      return Promise.resolve(extracciones)
    })
}

beforeEach(() => {
  mockListarExtracciones()
  vi.mocked(agruparExtracciones).mockReset()
  vi.mocked(desagruparExtracciones).mockReset()
})

describe('puedeAgruparSeleccion (guard puro, D13)', () => {
  it('deshabilitado con menos de 2 filas seleccionadas', () => {
    expect(puedeAgruparSeleccion([OC_1])).toBe(false)
    expect(puedeAgruparSeleccion([])).toBe(false)
  })

  it('deshabilitado con tipos mixtos', () => {
    expect(puedeAgruparSeleccion([OC_1, LICITACION_1])).toBe(false)
  })

  it('habilitado con 2+ filas orden_compra', () => {
    expect(puedeAgruparSeleccion([OC_1, OC_2])).toBe(true)
  })
})

describe('grupoIdDe (7.13 — prioriza override local sobre el grupo_id persistido)', () => {
  it('sin override, usa el grupo_id persistido de la extracción', () => {
    const conGrupo: ExtraccionResumen = { ...OC_1, grupo_id: 'grupo-persistido' }
    expect(grupoIdDe(conGrupo, {})).toBe('grupo-persistido')
  })

  it('sin override y sin grupo_id persistido, devuelve null', () => {
    expect(grupoIdDe(OC_1, {})).toBeNull()
  })

  it('un override string gana sobre el grupo_id persistido', () => {
    const conGrupo: ExtraccionResumen = { ...OC_1, grupo_id: 'grupo-persistido' }
    expect(grupoIdDe(conGrupo, { [OC_1.id]: 'grupo-optimista' })).toBe('grupo-optimista')
  })

  it('un override explícito null gana sobre el grupo_id persistido (desagrupar optimista)', () => {
    const conGrupo: ExtraccionResumen = { ...OC_1, grupo_id: 'grupo-persistido' }
    expect(grupoIdDe(conGrupo, { [OC_1.id]: null })).toBeNull()
  })
})

async function irATab(nombre: RegExp) {
  fireEvent.click(screen.getByRole('tab', { name: nombre }))
}

describe('ValidarExtraccionListado (T2, corrección) — carga de datos en dos queries', () => {
  // Corrección (coordinador): un único query `limit:200` ordenado por
  // `created_at DESC` comparte la ventana entre pendientes y validadas -- una
  // vez que se acumulan ~200 filas más nuevas (las validadas nunca se borran),
  // una extracción PENDIENTE más vieja desaparece silenciosamente de la
  // pantalla. Se vuelve al split: pendientes con su propio límite alto,
  // validadas con el tope de 50 que ya tenía el diseño anterior (D11).
  it('pide pendientes (validado:false, limit:200) y validadas (validado:true, limit:50) por separado', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    expect(listarExtracciones).toHaveBeenCalledTimes(2)
    expect(listarExtracciones).toHaveBeenCalledWith({ validado: false, limit: 200 })
    expect(listarExtracciones).toHaveBeenCalledWith({ validado: true, limit: 50 })
  })

  it('"Solo mías" activado pasa solo_mias:true a AMBAS queries (pendientes y validadas)', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText(/solo mías/i))

    await waitFor(() =>
      expect(listarExtracciones).toHaveBeenCalledWith({ validado: false, limit: 200, solo_mias: true }),
    )
    await waitFor(() =>
      expect(listarExtracciones).toHaveBeenCalledWith({ validado: true, limit: 50, solo_mias: true }),
    )
  })

  it('"Actualizar" refetchea ambas queries', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    vi.mocked(listarExtracciones).mockClear()
    fireEvent.click(screen.getByRole('button', { name: /actualizar/i }))

    await waitFor(() => expect(listarExtracciones).toHaveBeenCalledWith({ validado: false, limit: 200 }))
    await waitFor(() => expect(listarExtracciones).toHaveBeenCalledWith({ validado: true, limit: 50 }))
  })
})

describe('ValidarExtraccionListado (T2) — tabs por tipo de documento', () => {
  it('muestra una tab por tipo con la cantidad de extracciones de ese tipo', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    expect(screen.getByRole('tab', { name: /licitación \(1\)/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /directa \(0\)/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /comparativa \(0\)/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /orden de compra \(2\)/i })).toBeInTheDocument()
  })

  it('arranca en la tab Licitación y cambia el contenido al hacer click en otra tab', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    expect(screen.getByRole('tab', { name: /licitación/i })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByText('oc1.pdf')).not.toBeInTheDocument()

    await irATab(/orden de compra/i)

    expect(screen.getByText('oc1.pdf')).toBeInTheDocument()
    expect(screen.queryByText('lici1.pdf')).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /orden de compra/i })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('ValidarExtraccionListado (T2) — estado por fila y chips de filtro', () => {
  it('cada fila muestra un badge con su estado derivado', async () => {
    mockListarExtracciones([OC_1, PROCESANDO_1, ERROR_1, OC_VALIDADA_1])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    const filaProcesado = screen.getByText('oc1.pdf').closest('tr') as HTMLElement
    expect(within(filaProcesado).getByText('Procesado')).toBeInTheDocument()

    const filaProcesando = screen.getByText('oc-procesando.pdf').closest('tr') as HTMLElement
    expect(within(filaProcesando).getByText('Procesando')).toBeInTheDocument()

    const filaError = screen.getByText('oc-error.pdf').closest('tr') as HTMLElement
    expect(within(filaError).getByText('Error')).toBeInTheDocument()
    expect(within(filaError).getByText(ERROR_1.error_msg as string)).toBeInTheDocument()

    const filaValidada = screen.getByText('oc-validada-1.pdf').closest('tr') as HTMLElement
    expect(within(filaValidada).getByText('Validada')).toBeInTheDocument()
  })

  it('una fila failed sin error_msg muestra un mensaje genérico', async () => {
    const errorSinMensaje: ExtraccionResumen = { ...ERROR_1, id: 'ex-error-2', error_msg: null }
    mockListarExtracciones([errorSinMensaje])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc-error.pdf')).toBeInTheDocument())

    expect(screen.getByText(/no se pudo procesar/i)).toBeInTheDocument()
  })

  it('los chips de estado filtran las filas de la tab activa y muestran la cuenta', async () => {
    mockListarExtracciones([OC_1, PROCESANDO_1, ERROR_1, OC_VALIDADA_1])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    expect(screen.getByRole('button', { name: /^todos \(4\)$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^error \(1\)$/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^error \(1\)$/i }))

    expect(screen.getByText('oc-error.pdf')).toBeInTheDocument()
    expect(screen.queryByText('oc1.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('oc-procesando.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('oc-validada-1.pdf')).not.toBeInTheDocument()
  })
})

describe('ValidarExtraccionListado (T2) — acciones por fila', () => {
  it('procesado/procesado con advertencias tienen link "Revisar"; procesando/error no', async () => {
    const advertencia: ExtraccionResumen = { ...OC_1, id: 'ex-adv', source_filename: 'oc-adv.pdf', status: 'partial' }
    mockListarExtracciones([OC_1, advertencia, PROCESANDO_1, ERROR_1])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    const filaProcesado = screen.getByText('oc1.pdf').closest('tr') as HTMLElement
    expect(within(filaProcesado).getByRole('link', { name: /revisar/i })).toHaveAttribute(
      'href',
      '/validar-extraccion/ex-1',
    )

    const filaAdvertencia = screen.getByText('oc-adv.pdf').closest('tr') as HTMLElement
    expect(within(filaAdvertencia).getByRole('link', { name: /revisar/i })).toBeInTheDocument()

    const filaProcesando = screen.getByText('oc-procesando.pdf').closest('tr') as HTMLElement
    expect(within(filaProcesando).queryByRole('link')).not.toBeInTheDocument()

    const filaError = screen.getByText('oc-error.pdf').closest('tr') as HTMLElement
    expect(within(filaError).queryByRole('link')).not.toBeInTheDocument()
  })

  it('una OC validada con orden_compra_id muestra el link de matching', async () => {
    mockListarExtracciones([OC_VALIDADA_1])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc-validada-1.pdf')).toBeInTheDocument())

    const link = screen.getByRole('link', { name: /matching/i })
    expect(link).toHaveAttribute('href', '/ordenes-compra/oc-abc/matching')
  })

  it('una OC validada sin orden_compra_id (miembro no ancla) no muestra un link roto', async () => {
    const sinAncla: ExtraccionResumen = { ...OC_VALIDADA_1, id: 'ex-validada-2', orden_compra_id: null }
    mockListarExtracciones([sinAncla])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc-validada-1.pdf')).toBeInTheDocument())

    expect(screen.queryByRole('link', { name: /matching/i })).not.toBeInTheDocument()
  })

  it('una licitación validada es informativa: badge "Validada" sin ninguna acción', async () => {
    const licitacionValidada: ExtraccionResumen = {
      ...LICITACION_1,
      id: 'ex-lici-validada',
      validado: true,
      source_filename: 'lici-validada.pdf',
    }
    mockListarExtracciones([LICITACION_1, licitacionValidada])
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici-validada.pdf')).toBeInTheDocument())

    const fila = screen.getByText('lici-validada.pdf').closest('tr') as HTMLElement
    expect(within(fila).getByText('Validada')).toBeInTheDocument()
    expect(within(fila).queryByRole('link')).not.toBeInTheDocument()
  })

  it('muestra quién subió cada extracción, o "—" cuando no hay uploader', async () => {
    mockListarExtracciones([OC_1, SIN_UPLOADER])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    const filaConUploader = screen.getByText('oc1.pdf').closest('tr') as HTMLElement
    expect(within(filaConUploader).getByText('Ana Gómez')).toBeInTheDocument()

    const filaSinUploader = screen.getByText('oc-sin-uploader.pdf').closest('tr') as HTMLElement
    expect(within(filaSinUploader).getAllByText('—').length).toBeGreaterThan(0)
  })
})

describe('ValidarExtraccionListado (D13) — agrupar/desagrupar, ahora solo en la tab Orden de compra', () => {
  it('los botones Agrupar/Desagrupar y los checkboxes no aparecen fuera de la tab Orden de compra', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /agrupar seleccionadas/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^desagrupar$/i })).not.toBeInTheDocument()
  })

  it('"Agrupar seleccionadas" arranca deshabilitado y se habilita al tildar 2 filas orden_compra', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    const boton = screen.getByRole('button', { name: /agrupar seleccionadas/i })
    expect(boton).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    expect(boton).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))
    expect(boton).not.toBeDisabled()
  })

  it('solo las filas orden_compra en estado validable tienen checkbox (no procesando/error/validada)', async () => {
    mockListarExtracciones([OC_1, PROCESANDO_1, ERROR_1, OC_VALIDADA_1])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    expect(screen.getByLabelText(/seleccionar oc1\.pdf/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/seleccionar oc-procesando\.pdf/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/seleccionar oc-error\.pdf/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/seleccionar oc-validada-1\.pdf/i)).not.toBeInTheDocument()
  })

  it('tras agrupar, la tabla colapsa las filas en un encabezado de grupo (T3); reseleccionar con el checkbox del encabezado habilita "Desagrupar"', async () => {
    vi.mocked(agruparExtracciones).mockResolvedValue({ grupo_id: 'grupo-1' })

    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))
    fireEvent.click(screen.getByRole('button', { name: /agrupar seleccionadas/i }))

    await waitFor(() => expect(agruparExtracciones).toHaveBeenCalledWith(['ex-1', 'ex-2']))
    // T3 -- ya no hay un tag "Grupo" por fila: las 2 filas se colapsan en UN
    // encabezado de grupo, así que las filas individuales (con esos nombres
    // de archivo exactos) dejan de estar en el documento.
    await waitFor(() => expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument())
    expect(screen.queryByText('oc1.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('oc2.pdf')).not.toBeInTheDocument()

    const botonDesagrupar = screen.getByRole('button', { name: /^desagrupar$/i })
    expect(botonDesagrupar).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar grupo/i))
    expect(botonDesagrupar).not.toBeDisabled()

    fireEvent.click(botonDesagrupar)
    await waitFor(() => expect(desagruparExtracciones).toHaveBeenCalledWith(['ex-1', 'ex-2']))
    await waitFor(() => expect(screen.queryByText(/grupo · /i)).not.toBeInTheDocument())
    expect(screen.getByText('oc1.pdf')).toBeInTheDocument()
    expect(screen.getByText('oc2.pdf')).toBeInTheDocument()
  })

  it('agrupar envía solo las filas seleccionadas que siguen visibles (no las que ocultó "Solo mías")', async () => {
    // Revisión (R3-stale-selection-sent-to-mutation): una fila tildada que
    // después sale del listado (filtro "Solo mías", o un cambio de estado por
    // el polling) no debe viajar en el request de agrupar/desagrupar.
    const MIA_1: ExtraccionResumen = { ...OC_1, id: 'ex-mia-1', source_filename: 'mia1.pdf' }
    const MIA_2: ExtraccionResumen = { ...OC_1, id: 'ex-mia-2', source_filename: 'mia2.pdf' }
    vi.mocked(listarExtracciones)
      .mockReset()
      .mockImplementation((params: ListarExtraccionesParams = {}) => {
        if (params.validado === true) return Promise.resolve([])
        return Promise.resolve(params.solo_mias ? [MIA_1, MIA_2] : [OC_1, OC_2, MIA_1, MIA_2])
      })
    vi.mocked(agruparExtracciones).mockResolvedValue({ grupo_id: 'grupo-1' })

    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))
    fireEvent.click(screen.getByLabelText(/solo mías/i))
    await waitFor(() => expect(screen.getByLabelText(/seleccionar mia1\.pdf/i)).toBeInTheDocument())
    expect(screen.queryByText('oc1.pdf')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText(/seleccionar mia1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar mia2\.pdf/i))
    fireEvent.click(screen.getByRole('button', { name: /agrupar seleccionadas/i }))

    await waitFor(() => expect(agruparExtracciones).toHaveBeenCalledWith(['ex-mia-1', 'ex-mia-2']))
  })

  it('7.13: el encabezado de grupo (T3) lee el grupo_id persistido de un refetch/recarga, sin pasar por agrupar/desagrupar primero', async () => {
    const OC_1_AGRUPADA: ExtraccionResumen = { ...OC_1, grupo_id: 'grupo-persistido' }
    const OC_2_AGRUPADA: ExtraccionResumen = { ...OC_2, grupo_id: 'grupo-persistido' }
    mockListarExtracciones([OC_1_AGRUPADA, OC_2_AGRUPADA, LICITACION_1])

    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument())

    // El grupo viene de la respuesta del listado (simula un reload), no de
    // haber pasado por el botón "Agrupar seleccionadas" en esta sesión.
    expect(agruparExtracciones).not.toHaveBeenCalled()

    fireEvent.click(screen.getByLabelText(/seleccionar grupo/i))

    expect(screen.getByRole('button', { name: /^desagrupar$/i })).not.toBeDisabled()
  })
})

describe('ValidarExtraccionListado (T3) — filas de grupo colapsables en la tab Orden de compra', () => {
  const OC_A1: ExtraccionResumen = { ...OC_1, id: 'ex-a1', source_filename: 'grupoA-1.pdf', grupo_id: 'grupo-a' }
  const OC_A2: ExtraccionResumen = { ...OC_1, id: 'ex-a2', source_filename: 'grupoA-2.pdf', grupo_id: 'grupo-a' }
  const OC_B1: ExtraccionResumen = { ...OC_1, id: 'ex-b1', source_filename: 'grupoB-1.pdf', grupo_id: 'grupo-b' }
  const OC_B2: ExtraccionResumen = { ...OC_1, id: 'ex-b2', source_filename: 'grupoB-2.pdf', grupo_id: 'grupo-b' }

  it('dos grupos distintos se renderizan como dos encabezados separados, cada uno con su cantidad y sus archivos', async () => {
    mockListarExtracciones([OC_A1, OC_A2, OC_B1, OC_B2])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getAllByText(/grupo · 2 archivos/i).length).toBe(2))

    expect(screen.getByText(/grupoa-1\.pdf, grupoa-2\.pdf/i)).toBeInTheDocument()
    expect(screen.getByText(/grupob-1\.pdf, grupob-2\.pdf/i)).toBeInTheDocument()
  })

  it('un grupo arranca colapsado; el toggle lo expande y lo vuelve a contraer', async () => {
    mockListarExtracciones([OC_A1, OC_A2])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument())

    expect(screen.queryByLabelText(/seleccionar grupoa-1\.pdf/i)).not.toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: /expandir grupo/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)

    const toggleExpandido = screen.getByRole('button', { name: /contraer grupo/i })
    expect(toggleExpandido).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText(/seleccionar grupoa-1\.pdf/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/seleccionar grupoa-2\.pdf/i)).toBeInTheDocument()

    fireEvent.click(toggleExpandido)
    expect(screen.queryByLabelText(/seleccionar grupoa-1\.pdf/i)).not.toBeInTheDocument()
  })

  it('el checkbox del encabezado selecciona todos los miembros; "Desagrupar" envía exactamente esos ids', async () => {
    vi.mocked(desagruparExtracciones).mockResolvedValue(undefined)
    mockListarExtracciones([OC_A1, OC_A2])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument())

    const checkboxGrupo = screen.getByLabelText(/seleccionar grupo/i) as HTMLInputElement
    expect(checkboxGrupo.checked).toBe(false)

    fireEvent.click(checkboxGrupo)
    expect(checkboxGrupo.checked).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /^desagrupar$/i }))
    await waitFor(() => expect(desagruparExtracciones).toHaveBeenCalledWith(['ex-a1', 'ex-a2']))
  })

  it('un chip de estado muestra el grupo si CUALQUIER miembro matchea; al expandirlo se ven TODOS los miembros, no solo el que matchea', async () => {
    const A1_ERROR: ExtraccionResumen = { ...OC_A1, status: 'failed', error_msg: 'falló' }
    const A2_OK: ExtraccionResumen = { ...OC_A2 }
    mockListarExtracciones([A1_ERROR, A2_OK])
    renderConQueryClient(<ValidarExtraccionListado />)
    await irATab(/orden de compra/i)
    await waitFor(() => expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /^error \(1\)$/i }))
    expect(screen.getByText(/grupo · 2 archivos/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /expandir grupo/i }))
    // grupoA-1 (el que matchea "Error") y grupoA-2 (el que NO matchea, pero
    // es parte del mismo grupo) aparecen los dos como filas individuales.
    expect(screen.getByText('grupoA-1.pdf')).toBeInTheDocument()
    expect(screen.getByText('grupoA-2.pdf')).toBeInTheDocument()
    // grupoA-2 quedó en estado "procesado" (validable), así que sigue
    // teniendo su propio checkbox aunque no matchee el chip "Error".
    expect(screen.getByLabelText(/seleccionar grupoa-2\.pdf/i)).toBeInTheDocument()
  })
})
