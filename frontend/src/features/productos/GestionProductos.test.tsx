import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GestionProductos } from './GestionProductos'

const { perfilMock } = vi.hoisted(() => ({
  perfilMock: { id: 'user-1', rol: 'admin' as string },
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
}))

vi.mock('@/features/auth/AuthContext', async () => {
  const { authDeRol } = await import('@/test/capacidades')
  return { useAuth: () => ({ perfil: perfilMock, ...authDeRol(perfilMock.rol) }) }
})

vi.mock('@/lib/api/productos', () => ({
  listarProductos: vi.fn(),
  listarCategorias: vi.fn(),
  listarMarcas: vi.fn(),
  listarEnvases: vi.fn(),
  crearCategoria: vi.fn(),
  actualizarCategoria: vi.fn(),
}))

import {
  listarCategorias,
  listarEnvases,
  listarMarcas,
  listarProductos,
} from '@/lib/api/productos'

const PRODUCTO_A = {
  id: 'prod-1',
  drogueria_id: 'drog-1',
  codigo_interno: 'A001',
  nombre: 'Ibuprofeno 400mg',
  categoria_id: null,
  clasificacion: 'medicamento' as const,
  droga: null,
  presentacion: null,
  forma_farmaceutica: null,
  marca_id: null,
  envase_id: null,
  alicuota_iva: null,
  codigo_anmat: null,
  activo: true,
}

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(listarProductos).mockReset().mockResolvedValue({ items: [PRODUCTO_A], total: 1 })
  vi.mocked(listarCategorias).mockReset().mockResolvedValue([])
  vi.mocked(listarMarcas).mockReset().mockResolvedValue([])
  vi.mocked(listarEnvases).mockReset().mockResolvedValue([])
})

describe('GestionProductos', () => {
  it('renderiza el listado de productos', async () => {
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())
    expect(screen.getByText('A001')).toBeInTheDocument()
  })

  it('muestra controles de paginación y pide la página siguiente al backend', async () => {
    const PRODUCTO_B = { ...PRODUCTO_A, id: 'prod-2', codigo_interno: 'B002', nombre: 'Paracetamol 500mg' }
    vi.mocked(listarProductos).mockImplementation(({ page } = {}) =>
      Promise.resolve({ items: page === 2 ? [PRODUCTO_B] : [PRODUCTO_A], total: 51 }),
    )
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())
    expect(screen.getByText(/página 1 de 2/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /siguiente/i }))

    await waitFor(() => expect(screen.getByText('Paracetamol 500mg')).toBeInTheDocument())
    expect(listarProductos).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }))
  })

  it('S6: ni un rol con escritura ve alta, edición o borrado; el listado avisa que los productos vienen de Progress', async () => {
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /nuevo producto/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument()
    expect(screen.getByText('Los productos se dan de alta y se editan en Progress.')).toBeInTheDocument()
  })
})
