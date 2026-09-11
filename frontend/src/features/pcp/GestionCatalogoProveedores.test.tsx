import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GestionCatalogoProveedores } from './GestionCatalogoProveedores'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/productos', () => ({ listarProductos: vi.fn() }))
vi.mock('@/lib/api/terceros', () => ({ listarTerceros: vi.fn() }))
vi.mock('@/lib/api/pcp', () => ({ listarProveedoresProducto: vi.fn(), agregarProveedorProducto: vi.fn() }))

import { agregarProveedorProducto, listarProveedoresProducto, type ProductoProveedor } from '@/lib/api/pcp'
import { listarProductos } from '@/lib/api/productos'
import { listarTerceros } from '@/lib/api/terceros'

const PRODUCTOS = [
  { id: 'prod-1', codigo_interno: 'AMOX', nombre: 'Amoxicilina' },
  { id: 'prod-2', codigo_interno: 'IBU', nombre: 'Ibuprofeno' },
]
const PROVEEDOR = { id: 'prov-1', razon_social: 'Laboratorio Norte', tiene_rol_proveedor: true }
const ASOCIACION: ProductoProveedor = {
  id: 'pp-1', drogueria_id: 'drog-1', producto_id: 'prod-1', proveedor_id: 'prov-1',
  codigo_proveedor: 'N-15', preferido: false, activo: true, notas: null,
}

function renderCatalogo() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><GestionCatalogoProveedores /></QueryClientProvider>)
}

describe('GestionCatalogoProveedores', () => {
  let catalogo: typeof ASOCIACION[]

  beforeEach(() => {
    catalogo = [ASOCIACION]
    perfilMock.rol = 'admin'
    vi.mocked(listarProductos).mockReset().mockResolvedValue(PRODUCTOS as never)
    vi.mocked(listarTerceros).mockReset().mockResolvedValue([PROVEEDOR] as never)
    vi.mocked(listarProveedoresProducto).mockReset().mockImplementation(async (productoId) =>
      catalogo.filter((asociacion) => asociacion.producto_id === productoId),
    )
    vi.mocked(agregarProveedorProducto).mockReset().mockImplementation(async (productoId, payload) => {
      const asociacion = { ...ASOCIACION, id: 'pp-2', producto_id: productoId, ...payload }
      catalogo = [...catalogo, asociacion]
      return asociacion
    })
  })

  it('muestra el catálogo poblado y el vacío al cambiar de producto', async () => {
    renderCatalogo()
    expect(await screen.findByText('Laboratorio Norte')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/producto/i), { target: { value: 'prod-2' } })
    await waitFor(() => expect(listarProveedoresProducto).toHaveBeenLastCalledWith('prod-2'))
    expect(await screen.findByText(/no hay proveedores asociados/i)).toBeInTheDocument()
  })

  it('muestra el estado vacío de productos sin consultar asociaciones', async () => {
    vi.mocked(listarProductos).mockResolvedValue([] as never)
    renderCatalogo()

    expect(await screen.findByText(/no hay productos disponibles/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/producto/i)).toBeDisabled()
    expect(screen.queryByRole('button', { name: /agregar proveedor/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/cargando proveedores/i)).not.toBeInTheDocument()
    expect(listarProveedoresProducto).not.toHaveBeenCalled()
  })

  it('asocia un proveedor para escritura y refresca solo el catálogo del producto', async () => {
    catalogo = []
    renderCatalogo()
    await screen.findByText(/no hay proveedores asociados/i)

    fireEvent.click(screen.getByRole('button', { name: /agregar proveedor/i }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Proveedor' }), { target: { value: 'prov-1' } })
    fireEvent.click(screen.getByRole('button', { name: /^asociar$/i }))

    await waitFor(() => expect(agregarProveedorProducto).toHaveBeenCalledWith('prod-1', { proveedor_id: 'prov-1' }))
    expect(await screen.findByText('Laboratorio Norte')).toBeInTheDocument()
  })

  it('asocia al producto elegido después de cambiar el catálogo', async () => {
    catalogo = []
    renderCatalogo()
    await screen.findByText(/no hay proveedores asociados/i)
    fireEvent.change(screen.getByLabelText(/producto/i), { target: { value: 'prod-2' } })
    await screen.findByText(/no hay proveedores asociados/i)
    fireEvent.click(screen.getByRole('button', { name: /agregar proveedor/i }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Proveedor' }), { target: { value: 'prov-1' } })
    fireEvent.click(screen.getByRole('button', { name: /^asociar$/i }))

    await waitFor(() => expect(agregarProveedorProducto).toHaveBeenCalledWith('prod-2', { proveedor_id: 'prov-1' }))
    expect(await screen.findByText('Laboratorio Norte')).toBeInTheDocument()
  })

  it('oculta la asociación para roles de solo lectura', async () => {
    perfilMock.rol = 'superadmin'
    renderCatalogo()

    await screen.findByText('Laboratorio Norte')
    expect(screen.queryByRole('button', { name: /agregar proveedor/i })).not.toBeInTheDocument()
  })

  it('muestra el conflicto sin alterar el listado actual', async () => {
    vi.mocked(agregarProveedorProducto).mockRejectedValue(new Error('El proveedor ya está asociado'))
    renderCatalogo()
    await screen.findByText('Laboratorio Norte')

    fireEvent.click(screen.getByRole('button', { name: /agregar proveedor/i }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Proveedor' }), { target: { value: 'prov-1' } })
    fireEvent.click(screen.getByRole('button', { name: /^asociar$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('El proveedor ya está asociado')
    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(within(screen.getByRole('list', { name: 'Proveedores asociados' })).getAllByRole('listitem')).toHaveLength(1)
  })
})
