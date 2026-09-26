import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentoReciente } from '@/lib/api/extraccion'
import { RecentCard } from './RecentCard'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/api/extraccion', () => ({
  listarDocumentosRecientes: vi.fn(),
}))

import { listarDocumentosRecientes } from '@/lib/api/extraccion'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

// Un `DocumentoReciente` real (services/extraccion/main.py::listar_documentos,
// carga-asincrona T1) -- `status` viene de `extraction_results.status`
// (migración 0028) y `error_msg` es el mensaje en español ya mapeado.
function documentoReciente(overrides: Partial<DocumentoReciente> = {}): DocumentoReciente {
  return {
    id: 'ext-1',
    source_filename: 'a.pdf',
    document_type: 'orden_compra',
    row_count: 3,
    status: 'completed',
    error_msg: null,
    created_at: '2026-09-21T00:00:00Z',
    proceso_comercial: null,
    ...overrides,
  }
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(listarDocumentosRecientes).mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('RecentCard — status por fila (carga-asincrona T2)', () => {
  it('una fila "processing" muestra el estado Procesando', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'processing' })],
    })

    renderConQueryClient(<RecentCard />)

    expect(await screen.findByText(/procesando/i)).toBeInTheDocument()
  })

  it('una fila "completed" muestra Listo para validar', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'completed' })],
    })

    renderConQueryClient(<RecentCard />)

    expect(await screen.findByText(/listo para validar/i)).toBeInTheDocument()
  })

  it('una fila "partial" también muestra Listo para validar', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'partial' })],
    })

    renderConQueryClient(<RecentCard />)

    expect(await screen.findByText(/listo para validar/i)).toBeInTheDocument()
  })

  it('una fila "failed" muestra Error y el error_msg visible en el texto (no solo en un tooltip)', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [
        documentoReciente({
          status: 'failed',
          error_msg: 'No se detectaron proveedores en el documento',
        }),
      ],
    })

    renderConQueryClient(<RecentCard />)

    expect(await screen.findByText(/^error$/i)).toBeInTheDocument()
    const mensaje = await screen.findByText(/no se detectaron proveedores en el documento/i)
    // El mensaje tiene que estar en el texto visible del documento, no
    // escondido en un atributo title/aria-label sin texto acompañante.
    expect(mensaje.textContent).toMatch(/no se detectaron proveedores/i)
  })

  it('el status nunca depende solo del color: cada estado tiene su propio texto', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [
        documentoReciente({ id: 'a', status: 'processing' }),
        documentoReciente({ id: 'b', status: 'completed' }),
        documentoReciente({ id: 'c', status: 'failed', error_msg: 'boom' }),
      ],
    })

    renderConQueryClient(<RecentCard />)

    await waitFor(() => expect(screen.getByText(/procesando/i)).toBeInTheDocument())
    expect(screen.getByText(/listo para validar/i)).toBeInTheDocument()
    expect(screen.getByText(/^error$/i)).toBeInTheDocument()
  })
})

describe('RecentCard — acción Validar', () => {
  it('una fila "completed" ofrece un botón Validar que navega con extractionId y rowCount', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ id: 'ext-completa', status: 'completed', row_count: 9 })],
    })

    renderConQueryClient(<RecentCard />)

    const boton = await screen.findByRole('button', { name: /validar/i })
    boton.click()

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/validar-extraccion/$extractionId',
      params: { extractionId: 'ext-completa' },
      search: { rowCount: 9 },
    })
  })

  it('una fila "processing" NO ofrece el botón Validar', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'processing' })],
    })

    renderConQueryClient(<RecentCard />)

    await screen.findByText(/procesando/i)
    expect(screen.queryByRole('button', { name: /validar/i })).not.toBeInTheDocument()
  })

  it('una fila "failed" NO ofrece el botón Validar, sugiere volver a subir el archivo', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'failed', error_msg: 'Error interno del servidor' })],
    })

    renderConQueryClient(<RecentCard />)

    await screen.findByText(/^error$/i)
    expect(screen.queryByRole('button', { name: /validar/i })).not.toBeInTheDocument()
    expect(screen.getByText(/volv/i)).toBeInTheDocument()
  })
})

describe('RecentCard — polling condicional (solo mientras algo está "processing")', () => {
  it('con al menos una fila "processing" refetchea sola a los ~3s', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'processing' })],
    })

    renderConQueryClient(<RecentCard />)

    await vi.waitFor(() => expect(listarDocumentosRecientes).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(3000)
    await vi.waitFor(() => expect(listarDocumentosRecientes).toHaveBeenCalledTimes(2))
  })

  it('sin ninguna fila "processing" NO vuelve a pollear', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'completed' })],
    })

    renderConQueryClient(<RecentCard />)

    await vi.waitFor(() => expect(listarDocumentosRecientes).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(5000)
    expect(listarDocumentosRecientes).toHaveBeenCalledTimes(1)
  })

  it('cuando la fila "processing" termina (pasa a completed en un refetch), el polling se detiene', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listarDocumentosRecientes)
      .mockResolvedValueOnce({ documentos: [documentoReciente({ status: 'processing' })] })
      .mockResolvedValue({ documentos: [documentoReciente({ status: 'completed' })] })

    renderConQueryClient(<RecentCard />)

    await vi.waitFor(() => expect(listarDocumentosRecientes).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(3000)
    await vi.waitFor(() => expect(listarDocumentosRecientes).toHaveBeenCalledTimes(2))

    await vi.advanceTimersByTimeAsync(5000)
    expect(listarDocumentosRecientes).toHaveBeenCalledTimes(2)
  })
})

describe('RecentCard — accesibilidad', () => {
  it('expone una región aria-live="polite" que refleja el estado', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'processing' })],
    })

    const { container } = renderConQueryClient(<RecentCard />)

    await screen.findByText(/procesando/i)
    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion).not.toBeNull()
    expect(liveRegion?.textContent).toMatch(/procesándose/i)
  })

  // T3 (revisión de T2): el resumen del aria-live contaba solo sobre las 3
  // filas visibles (`documentos.slice(0, 3)`) mientras `refetchInterval` mira
  // la lista completa -- con más de 3 documentos recientes, un "processing"
  // fuera del top-3 hacía pollear en segundo plano sin que el lector de
  // pantalla se enterara. Ambos deben leer la misma lista completa.
  it('el resumen del aria-live cuenta también un "processing" fuera de las 3 filas visibles', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [
        documentoReciente({ id: 'a', status: 'completed' }),
        documentoReciente({ id: 'b', status: 'completed' }),
        documentoReciente({ id: 'c', status: 'completed' }),
        documentoReciente({ id: 'd', status: 'processing' }),
      ],
    })

    const { container } = renderConQueryClient(<RecentCard />)

    await waitFor(() => {
      const liveRegion = container.querySelector('[aria-live="polite"]')
      expect(liveRegion?.textContent).toMatch(/1 documento procesándose/i)
    })
  })
})

describe('RecentCard — mensaje de error con fallback (T3)', () => {
  it('una fila "failed" con error_msg null muestra el mensaje de fallback', async () => {
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ status: 'failed', error_msg: null })],
    })

    renderConQueryClient(<RecentCard />)

    await screen.findByText(/^error$/i)
    expect(screen.getByText(/no se pudo procesar el documento/i)).toBeInTheDocument()
  })
})
