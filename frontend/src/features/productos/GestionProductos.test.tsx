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

vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: perfilMock }),
}))

vi.mock('@/lib/api/productos', () => ({
  listarProductos: vi.fn(),
  listarCategorias: vi.fn(),
  listarMarcas: vi.fn(),
  listarEnvases: vi.fn(),
  listarCaracteristicas: vi.fn(),
  listarCaracteristicasProducto: vi.fn(),
  crearProducto: vi.fn(),
  actualizarProducto: vi.fn(),
  eliminarProducto: vi.fn(),
  crearCategoria: vi.fn(),
  actualizarCategoria: vi.fn(),
  asignarCaracteristicaProducto: vi.fn(),
  quitarCaracteristicaProducto: vi.fn(),
}))

import {
  actualizarProducto,
  crearProducto,
  eliminarProducto,
  listarCaracteristicas,
  listarCaracteristicasProducto,
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
  vi.mocked(listarCaracteristicas).mockReset().mockResolvedValue([])
  vi.mocked(listarCaracteristicasProducto).mockReset().mockResolvedValue([])
  vi.mocked(crearProducto).mockReset().mockResolvedValue(PRODUCTO_A)
  vi.mocked(actualizarProducto).mockReset().mockResolvedValue(PRODUCTO_A)
  vi.mocked(eliminarProducto).mockReset().mockResolvedValue(undefined)
})

describe('GestionProductos', () => {
  it('renderiza el listado de productos', async () => {
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())
    expect(screen.getByText('A001')).toBeInTheDocument()
  })

  it('el diálogo de alta llama a crearProducto con los campos cargados', async () => {
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /nuevo producto/i }))
    fireEvent.change(screen.getByLabelText(/código interno/i), { target: { value: 'B002' } })
    fireEvent.change(screen.getByLabelText(/^nombre$/i), { target: { value: 'Paracetamol 500mg' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))

    await waitFor(() =>
      expect(crearProducto).toHaveBeenCalledWith(
        expect.objectContaining({ codigo_interno: 'B002', nombre: 'Paracetamol 500mg' }),
      ),
    )
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

  it('un rol sin permiso de escritura no ve las acciones de alta/edición/borrado', async () => {
    perfilMock.rol = 'comercial'
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /nuevo producto/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument()
  })
})
