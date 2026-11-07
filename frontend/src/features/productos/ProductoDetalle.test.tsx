import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProductoDetalle } from './ProductoDetalle'

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
  obtenerProducto: vi.fn(),
  listarCategorias: vi.fn(),
  listarMarcas: vi.fn(),
  listarEnvases: vi.fn(),
  listarCostos: vi.fn(),
  listarStock: vi.fn(),
  listarCaracteristicas: vi.fn(),
  listarCaracteristicasProducto: vi.fn(),
  asignarCaracteristicaProducto: vi.fn(),
  quitarCaracteristicaProducto: vi.fn(),
}))

import {
  asignarCaracteristicaProducto,
  listarCaracteristicas,
  listarCaracteristicasProducto,
  listarCategorias,
  listarCostos,
  listarEnvases,
  listarMarcas,
  listarStock,
  obtenerProducto,
  quitarCaracteristicaProducto,
} from '@/lib/api/productos'

const PRODUCTO = {
  id: 'prod-1',
  drogueria_id: 'drog-1',
  codigo_interno: 'A001',
  nombre: 'Ibuprofeno 400mg',
  categoria_id: 'cat-1',
  clasificacion: 'medicamento' as const,
  droga: 'Ibuprofeno',
  presentacion: 'Caja x 20',
  forma_farmaceutica: 'Comprimido',
  marca_id: 'marca-1',
  envase_id: 'env-1',
  alicuota_iva: 10.5,
  codigo_anmat: 'ANMAT-77',
  activo: true,
}

function renderDetalle() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ProductoDetalle productoId="prod-1" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerProducto).mockReset().mockResolvedValue(PRODUCTO)
  vi.mocked(listarCategorias).mockReset().mockResolvedValue([
    { id: 'cat-1', drogueria_id: 'drog-1', nombre: 'Analgésicos', descripcion: null, activa: true },
  ])
  vi.mocked(listarMarcas).mockReset().mockResolvedValue([
    { id: 'marca-1', drogueria_id: 'drog-1', nombre: 'Bagó', activa: true },
  ])
  vi.mocked(listarEnvases).mockReset().mockResolvedValue([
    { id: 'env-1', drogueria_id: 'drog-1', nombre: 'Blíster', activa: true },
  ])
  vi.mocked(listarCostos).mockReset().mockResolvedValue([
    {
      id: 'costo-1',
      producto_id: 'prod-1',
      costo_unitario: 123.45,
      fecha_desde: '2026-01-01',
      fecha_hasta: null,
      origen: 'import_sistema',
    },
  ])
  vi.mocked(listarStock).mockReset().mockResolvedValue([
    { id: 'stock-1', producto_id: 'prod-1', deposito: 'Central', cantidad_disponible: 40, cantidad_comprometida: 7 },
  ])
  vi.mocked(listarCaracteristicas).mockReset().mockResolvedValue([
    { id: 'car-1', drogueria_id: 'drog-1', nombre: 'Refrigerado', activa: true },
    { id: 'car-2', drogueria_id: 'drog-1', nombre: 'Psicotrópico', activa: true },
  ])
  vi.mocked(listarCaracteristicasProducto).mockReset().mockResolvedValue([
    { id: 'pc-1', producto_id: 'prod-1', caracteristica_id: 'car-1' },
  ])
  vi.mocked(asignarCaracteristicaProducto)
    .mockReset()
    .mockResolvedValue({ id: 'pc-2', producto_id: 'prod-1', caracteristica_id: 'car-2' })
  vi.mocked(quitarCaracteristicaProducto).mockReset().mockResolvedValue(undefined)
})

describe('ProductoDetalle (S6: datos de Progress de solo lectura)', () => {
  it('muestra los datos del producto, el historial de costos y el stock sin formularios', async () => {
    renderDetalle()

    await waitFor(() => expect(screen.getByText('Ibuprofeno 400mg')).toBeInTheDocument())
    expect(screen.getByText('Los productos se dan de alta y se editan en Progress.')).toBeInTheDocument()
    for (const valor of ['Ibuprofeno', 'Caja x 20', 'Comprimido', 'medicamento', '10.5', 'ANMAT-77', 'Activo']) {
      expect(screen.getByText(valor)).toBeInTheDocument()
    }
    await waitFor(() => expect(screen.getByText('Analgésicos')).toBeInTheDocument())
    expect(screen.getByText('Bagó')).toBeInTheDocument()
    expect(screen.getByText('Blíster')).toBeInTheDocument()

    await waitFor(() => expect(screen.getByText('123.45')).toBeInTheDocument())
    expect(screen.getByText('import_sistema')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Central')).toBeInTheDocument())
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: /cargar costo/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ajustar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('asigna y quita características desde la ficha', async () => {
    renderDetalle()

    const refrigerado = await screen.findByRole('checkbox', { name: 'Refrigerado' })
    await waitFor(() => expect(refrigerado).toBeChecked())
    const psicotropico = screen.getByRole('checkbox', { name: 'Psicotrópico' })
    expect(psicotropico).not.toBeChecked()

    fireEvent.click(psicotropico)
    await waitFor(() => expect(asignarCaracteristicaProducto).toHaveBeenCalledWith('prod-1', 'car-2'))
    await waitFor(() => expect(refrigerado).not.toBeDisabled())

    fireEvent.click(refrigerado)
    await waitFor(() => expect(quitarCaracteristicaProducto).toHaveBeenCalledWith('prod-1', 'car-1'))
  })

  it('un rol sin escritura ve las características pero no puede cambiarlas', async () => {
    perfilMock.rol = 'comercial'
    renderDetalle()

    const refrigerado = await screen.findByRole('checkbox', { name: 'Refrigerado' })
    await waitFor(() => expect(refrigerado).toBeChecked())
    expect(refrigerado).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Psicotrópico' })).toBeDisabled()
  })
})
