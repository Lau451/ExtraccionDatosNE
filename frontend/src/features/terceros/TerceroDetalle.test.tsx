import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TerceroDetalle } from './TerceroDetalle'

const { perfilMock } = vi.hoisted(() => ({
  perfilMock: { id: 'user-1', rol: 'admin' as string },
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
}))

vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: perfilMock }),
}))

const { ApiErrorMock } = vi.hoisted(() => ({
  ApiErrorMock: class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

vi.mock('@/lib/api/presupuestacion', () => ({
  presupuestacionFetch: vi.fn(),
  ApiError: ApiErrorMock,
}))

vi.mock('@/lib/api/terceros', () => ({
  obtenerTercero: vi.fn(),
  actualizarTercero: vi.fn(),
  obtenerRolCliente: vi.fn(),
  crearRolCliente: vi.fn(),
  actualizarRolCliente: vi.fn(),
  obtenerRolProveedor: vi.fn(),
  crearRolProveedor: vi.fn(),
  actualizarRolProveedor: vi.fn(),
  listarDirecciones: vi.fn(),
  crearDireccion: vi.fn(),
  eliminarDireccion: vi.fn(),
  listarUsosDireccion: vi.fn(),
  crearUsoDireccion: vi.fn(),
  eliminarUsoDireccion: vi.fn(),
  listarContactos: vi.fn(),
  crearContacto: vi.fn(),
  actualizarContacto: vi.fn(),
}))

vi.mock('@/lib/api/catalogosComerciales', () => ({
  listarCondicionesPago: vi.fn(),
  listarFormasPago: vi.fn(),
  listarSectoresContacto: vi.fn(),
}))

import {
  actualizarTercero,
  crearRolCliente,
  crearRolProveedor,
  listarContactos,
  listarDirecciones,
  obtenerRolCliente,
  obtenerRolProveedor,
  obtenerTercero,
} from '@/lib/api/terceros'
import { listarCondicionesPago, listarFormasPago, listarSectoresContacto } from '@/lib/api/catalogosComerciales'

const TERCERO = {
  id: 'tercero-1',
  drogueria_id: 'drog-1',
  codigo_interno: 'T001',
  razon_social: 'Hospital Central',
  nombre_fantasia: null,
  cuit: '30-11111111-1',
  email: null,
  telefono: null,
  sitio_web: null,
  notas: null,
  activo: true,
}

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerTercero).mockReset().mockResolvedValue(TERCERO)
  vi.mocked(actualizarTercero).mockReset().mockResolvedValue(TERCERO)
  vi.mocked(obtenerRolCliente).mockReset().mockRejectedValue(new ApiErrorMock('no encontrado', 404))
  vi.mocked(crearRolCliente).mockReset()
  vi.mocked(obtenerRolProveedor).mockReset().mockRejectedValue(new ApiErrorMock('no encontrado', 404))
  vi.mocked(crearRolProveedor).mockReset()
  vi.mocked(listarDirecciones).mockReset().mockResolvedValue([])
  vi.mocked(listarContactos).mockReset().mockResolvedValue([])
  vi.mocked(listarCondicionesPago).mockReset().mockResolvedValue([])
  vi.mocked(listarFormasPago).mockReset().mockResolvedValue([])
  vi.mocked(listarSectoresContacto).mockReset().mockResolvedValue([])
})

describe('TerceroDetalle', () => {
  it('muestra el estado vacío con el botón de asignar cuando no tiene rol cliente', async () => {
    renderConQueryClient(<TerceroDetalle terceroId="tercero-1" />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())

    await waitFor(() =>
      expect(screen.getByText(/no tiene rol cliente asignado/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: /asignar rol cliente/i })).toBeInTheDocument()
  })
})
