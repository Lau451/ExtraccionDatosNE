import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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

import { obtenerFilasExtraccion } from '@/lib/api/extracciones'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(obtenerFilasExtraccion).mockReset()
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
