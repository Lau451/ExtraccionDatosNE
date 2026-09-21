import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentoReciente } from '@/lib/api/extraccion'
import { FormCard } from './FormCard'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/api/extraccion', () => ({
  listarClientes: vi.fn().mockResolvedValue([]),
  listarDocumentosRecientes: vi.fn(),
  procesarDocumento: vi.fn(),
}))

import { listarDocumentosRecientes, procesarDocumento } from '@/lib/api/extraccion'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

function archivo(nombre: string) {
  return new File(['contenido'], nombre, { type: 'application/pdf' })
}

// Un `DocumentoReciente` real (services/extraccion/main.py::listar_documentos)
// -- el mismo shape que se guarda en `extraction_results` y que la ruta
// /validar-extraccion/$extractionId espera como `extractionId`/`rowCount`.
function documentoReciente(overrides: Partial<DocumentoReciente> = {}): DocumentoReciente {
  return {
    id: 'ext-1',
    source_filename: 'a.pdf',
    document_type: 'orden_compra',
    row_count: 3,
    status: 'ok',
    created_at: '2026-09-21T00:00:00Z',
    proceso_comercial: null,
    ...overrides,
  }
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(listarDocumentosRecientes).mockReset().mockResolvedValue({
    // countAntes arranca en 0 (sin cache previo) -- 10 > countAntes + N para
    // cualquier N chico de este test, así esperarNuevoDocumento no reintenta.
    documentos: new Array(10).fill({}),
  })
  vi.mocked(procesarDocumento).mockReset()
})

function abrirTabOrdenes() {
  fireEvent.click(screen.getByRole('button', { name: /orden de compra/i }))
}

describe('FormCard — carga múltiple de órdenes de compra (D13)', () => {
  it('con tipo="ordenes" el input de archivo acepta múltiples archivos', () => {
    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(true)
  })

  it('con tipo="licitaciones" el input NO es múltiple', () => {
    const { container } = renderConQueryClient(<FormCard />)

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(false)
  })

  it('con 3 archivos se disparan 3 procesarDocumento EN SECUENCIA con el mismo grupoId', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111')
    const orden: string[] = []
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      orden.push(`start:${file.name}`)
      await Promise.resolve()
      orden.push(`end:${file.name}`)
      return { ok: true, tipo: 'orden_compra' }
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const archivos = [archivo('a.pdf'), archivo('b.pdf'), archivo('c.pdf')]
    fireEvent.change(input, { target: { files: archivos } })

    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))

    expect(orden).toEqual([
      'start:a.pdf',
      'end:a.pdf',
      'start:b.pdf',
      'end:b.pdf',
      'start:c.pdf',
      'end:c.pdf',
    ])
    for (const llamada of vi.mocked(procesarDocumento).mock.calls) {
      expect(llamada[0].grupoId).toBe('11111111-1111-4111-8111-111111111111')
    }
  })

  it('un 409 de duplicado en el segundo archivo no aborta el tercero, y se reporta por archivo', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('22222222-2222-4222-8222-222222222222')
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      if (file.name === 'duplicado.pdf') {
        throw new Error('Ya existe un documento con este contenido (409)')
      }
      return { ok: true, tipo: 'orden_compra' }
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const archivos = [archivo('a.pdf'), archivo('duplicado.pdf'), archivo('c.pdf')]
    fireEvent.change(input, { target: { files: archivos } })

    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))

    await waitFor(() =>
      expect(screen.getByText(/duplicado\.pdf/).closest('li')).toHaveTextContent(/409/),
    )
    expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesado correctamente/i)
    expect(screen.getByText(/^c\.pdf/).closest('li')).toHaveTextContent(/procesado correctamente/i)
  })
})

// Ajuste post-shipping (2026-09-21): auto-navegación tras una carga exitosa
// de orden_compra, pedida por el usuario -- solo para tipo='ordenes'
// (licitación/comparativa no cambian, se quedan en "Carga de documentos").
describe('FormCard — auto-navegación post-carga (solo orden_compra)', () => {
  it('1 archivo tipo="ordenes" exitoso navega a /validar-extraccion/$extractionId con el id y row_count reales', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'orden_compra' })
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ id: 'ext-nueva-1', row_count: 7 })],
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(navigateMock).toHaveBeenCalledTimes(1))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/validar-extraccion/$extractionId',
      params: { extractionId: 'ext-nueva-1' },
      search: { rowCount: 7 },
    })
  })

  it('N archivos agrupados (mismo grupoId), TODOS exitosos, navega UNA sola vez', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('33333333-3333-4333-8333-333333333333')
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'orden_compra' })
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [
        documentoReciente({ id: 'ext-grupo-c', row_count: 2 }),
        documentoReciente({ id: 'ext-grupo-b', row_count: 5 }),
        documentoReciente({ id: 'ext-grupo-a', row_count: 1 }),
      ],
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [archivo('a.pdf'), archivo('b.pdf'), archivo('c.pdf')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledTimes(1))
    // Cualquiera de los N sirve como entrada (mismo grupo) -- este mock
    // devuelve el primero de la lista.
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/validar-extraccion/$extractionId',
      params: { extractionId: 'ext-grupo-c' },
      search: { rowCount: 2 },
    })
  })

  it('si UNO de los N falla, no navega -- se queda en la pantalla de carga con el error por archivo', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('44444444-4444-4444-8444-444444444444')
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      if (file.name === 'duplicado.pdf') {
        throw new Error('Ya existe un documento con este contenido (409)')
      }
      return { ok: true, tipo: 'orden_compra' }
    })
    // Array grande (no filas realistas) -- alcanza countAntes+cantidadEsperada
    // de inmediato, así esperarNuevoDocumento no reintenta (mismo patrón que
    // el resto de los tests de este archivo). No importa el contenido: falla
    // 1 de los 3, así que no se navega de todos modos.
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: new Array(10).fill({}),
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [archivo('a.pdf'), archivo('duplicado.pdf'), archivo('c.pdf')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() =>
      expect(screen.getByText(/duplicado\.pdf/).closest('li')).toHaveTextContent(/409/),
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('tipo="licitaciones" exitoso NO navega (la auto-navegación es solo para orden_compra)', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'licitacion' })
    vi.mocked(listarDocumentosRecientes).mockResolvedValue({
      documentos: [documentoReciente({ id: 'ext-lici', document_type: 'licitacion', row_count: 4 })],
    })

    const { container } = renderConQueryClient(<FormCard />)
    // tipo='licitaciones' es el default -- no hace falta abrirTabOrdenes().

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesado correctamente/i),
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
