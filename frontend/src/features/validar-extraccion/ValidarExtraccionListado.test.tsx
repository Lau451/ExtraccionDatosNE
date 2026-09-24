import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ValidarExtraccionListado, puedeAgruparSeleccion, grupoIdDe } from './ValidarExtraccionListado'
import type { ExtraccionResumen } from '@/lib/api/extracciones'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
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

const OC_1: ExtraccionResumen = {
  id: 'ex-1',
  document_type: 'orden_compra',
  source_filename: 'oc1.pdf',
  row_count: 2,
  status: 'completado',
  validado: false,
  proceso_comercial_id: null,
  proceso_comercial_nombre: null,
  created_at: '2026-01-01T00:00:00Z',
  // Phase 6 (D11, tasks.md 6.2) hizo el campo requerido en el tipo TS al
  // sincronizarlo con el backend; se agrega acá solo para que el fixture siga
  // tipando -- Phase 8 es quien consume este campo para el link de
  // re-entrada, fuera del alcance de esta tarea.
  orden_compra_id: null,
}
const OC_2: ExtraccionResumen = { ...OC_1, id: 'ex-2', source_filename: 'oc2.pdf' }
const LICITACION_1: ExtraccionResumen = {
  ...OC_1,
  id: 'ex-3',
  document_type: 'licitacion',
  source_filename: 'lici1.pdf',
}

beforeEach(() => {
  vi.mocked(listarExtracciones).mockReset().mockResolvedValue([OC_1, OC_2, LICITACION_1])
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

describe('ValidarExtraccionListado (D13) — agrupar/desagrupar', () => {
  it('"Agrupar seleccionadas" arranca deshabilitado y se habilita al tildar 2 filas orden_compra', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    const boton = screen.getByRole('button', { name: /agrupar seleccionadas/i })
    expect(boton).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    expect(boton).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))
    expect(boton).not.toBeDisabled()
  })

  it('las filas de tipo licitacion no tienen checkbox para seleccionar', async () => {
    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('lici1.pdf')).toBeInTheDocument())

    expect(screen.queryByLabelText(/seleccionar lici1\.pdf/i)).not.toBeInTheDocument()
  })

  it('tras agrupar, las filas muestran el indicador de grupo y "Desagrupar" se habilita al reseleccionarlas', async () => {
    vi.mocked(agruparExtracciones).mockResolvedValue({ grupo_id: 'grupo-1' })

    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))
    fireEvent.click(screen.getByRole('button', { name: /agrupar seleccionadas/i }))

    await waitFor(() => expect(agruparExtracciones).toHaveBeenCalledWith(['ex-1', 'ex-2']))
    await waitFor(() => expect(screen.getAllByText('Grupo').length).toBe(2))

    const botonDesagrupar = screen.getByRole('button', { name: /^desagrupar$/i })
    expect(botonDesagrupar).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))

    expect(botonDesagrupar).not.toBeDisabled()

    fireEvent.click(botonDesagrupar)
    await waitFor(() => expect(desagruparExtracciones).toHaveBeenCalledWith(['ex-1', 'ex-2']))
    await waitFor(() => expect(screen.queryAllByText('Grupo').length).toBe(0))
  })

  it('7.13: el indicador de grupo y "Desagrupar" leen el grupo_id persistido de un refetch/recarga, sin pasar por agrupar/desagrupar primero', async () => {
    const OC_1_AGRUPADA: ExtraccionResumen = { ...OC_1, grupo_id: 'grupo-persistido' }
    const OC_2_AGRUPADA: ExtraccionResumen = { ...OC_2, grupo_id: 'grupo-persistido' }
    vi.mocked(listarExtracciones).mockReset().mockResolvedValue([
      OC_1_AGRUPADA,
      OC_2_AGRUPADA,
      LICITACION_1,
    ])

    renderConQueryClient(<ValidarExtraccionListado />)
    await waitFor(() => expect(screen.getByText('oc1.pdf')).toBeInTheDocument())

    // El grupo viene de la respuesta del listado (simula un reload), no de
    // haber pasado por el botón "Agrupar seleccionadas" en esta sesión.
    expect(agruparExtracciones).not.toHaveBeenCalled()
    expect(screen.getAllByText('Grupo').length).toBe(2)

    fireEvent.click(screen.getByLabelText(/seleccionar oc1\.pdf/i))
    fireEvent.click(screen.getByLabelText(/seleccionar oc2\.pdf/i))

    expect(screen.getByRole('button', { name: /^desagrupar$/i })).not.toBeDisabled()
  })
})
