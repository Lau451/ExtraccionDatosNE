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
  crearProducto: vi.fn(),
  actualizarProducto: vi.fn(),
  eliminarProducto: vi.fn(),
  crearCategoria: vi.fn(),
  actualizarCategoria: vi.fn(),
}))

import {
  actualizarProducto,
  crearProducto,
  eliminarProducto,
  listarCategorias,
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
  laboratorio: 'Lab X',
  codigo_anmat: null,
  activo: true,
}

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(listarProductos).mockReset().mockResolvedValue([PRODUCTO_A])
  vi.mocked(listarCategorias).mockReset().mockResolvedValue([])
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

  it('un rol sin permiso de escritura no ve las acciones de alta/edición/borrado', async () => {
    perfilMock.rol = 'comercial'
    renderConQueryClient(<GestionProductos />)

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /nuevo producto/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument()
  })
})
