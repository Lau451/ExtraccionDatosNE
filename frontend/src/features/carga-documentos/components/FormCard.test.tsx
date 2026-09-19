import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FormCard } from './FormCard'

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

beforeEach(() => {
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
