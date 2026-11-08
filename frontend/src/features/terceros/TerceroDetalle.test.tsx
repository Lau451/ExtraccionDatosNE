import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TerceroDetalle } from './TerceroDetalle'

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
  actualizarRolCliente: vi.fn(),
  obtenerRolProveedor: vi.fn(),
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
  actualizarRolCliente,
  actualizarRolProveedor,
  actualizarTercero,
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

const ROL_CLIENTE = {
  id: 'cli-1',
  drogueria_id: 'drog-1',
  tipo: 'hospital' as const,
  condicion_pago_id: 'cp-1',
  forma_pago_id: 'fp-1',
  activo: true,
}

const ROL_PROVEEDOR = {
  id: 'prov-1',
  drogueria_id: 'drog-1',
  tipo: 'laboratorio' as const,
  es_competidor: true,
  es_proveedor_compra: false,
  condicion_pago_id: 'cp-1',
  forma_pago_id: 'fp-1',
  activo: true,
}

const CONDICION = {
  id: 'cp-1',
  drogueria_id: 'drog-1',
  nombre: '30 días',
  plazos_dias: [30],
  descripcion: null,
  activo: true,
}

const FORMA = {
  id: 'fp-1',
  drogueria_id: 'drog-1',
  nombre: 'Transferencia',
  tipo: 'transferencia' as const,
  descripcion: null,
  activo: true,
}

const CAMPOS_APP_TERCERO = ['nombre_fantasia', 'email', 'telefono', 'sitio_web', 'notas']
const CAMPOS_APP_ROL = ['condicion_pago_id', 'forma_pago_id']

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerTercero).mockReset().mockResolvedValue(TERCERO)
  vi.mocked(actualizarTercero).mockReset().mockResolvedValue(TERCERO)
  vi.mocked(obtenerRolCliente).mockReset().mockRejectedValue(new ApiErrorMock('no encontrado', 404))
  vi.mocked(actualizarRolCliente).mockReset().mockResolvedValue(ROL_CLIENTE)
  vi.mocked(obtenerRolProveedor).mockReset().mockRejectedValue(new ApiErrorMock('no encontrado', 404))
  vi.mocked(actualizarRolProveedor).mockReset().mockResolvedValue(ROL_PROVEEDOR)
  vi.mocked(listarDirecciones).mockReset().mockResolvedValue([])
  vi.mocked(listarContactos).mockReset().mockResolvedValue([])
  vi.mocked(listarCondicionesPago).mockReset().mockResolvedValue([CONDICION])
  vi.mocked(listarFormasPago).mockReset().mockResolvedValue([FORMA])
  vi.mocked(listarSectoresContacto).mockReset().mockResolvedValue([])
})

describe('TerceroDetalle', () => {
  it('S7: sin rol cliente ni proveedor muestra el estado vacío y no ofrece asignarlos', async () => {
    renderConQueryClient(<TerceroDetalle terceroId="tercero-1" />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())

    await waitFor(() =>
      expect(screen.getByText(/no tiene rol cliente asignado/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/no tiene rol proveedor asignado/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /asignar rol/i })).not.toBeInTheDocument()
  })

  it('S7: la edición muestra la identidad de Progress de solo lectura y envía solo campos de la app', async () => {
    renderConQueryClient(<TerceroDetalle terceroId="tercero-1" />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /editar datos generales/i }))

    const dialogo = within(screen.getByRole('dialog'))
    expect(dialogo.getByText('Hospital Central')).toBeInTheDocument()
    expect(dialogo.getByText('T001')).toBeInTheDocument()
    expect(dialogo.getByText('30-11111111-1')).toBeInTheDocument()
    expect(dialogo.queryByRole('textbox', { name: /razón social/i })).not.toBeInTheDocument()
    expect(dialogo.queryByRole('textbox', { name: /código interno/i })).not.toBeInTheDocument()
    expect(dialogo.queryByRole('textbox', { name: /cuit/i })).not.toBeInTheDocument()

    fireEvent.change(dialogo.getByRole('textbox', { name: /email/i }), {
      target: { value: 'compras@hospital.org' },
    })
    fireEvent.click(dialogo.getByRole('button', { name: /^guardar$/i }))

    await waitFor(() => expect(actualizarTercero).toHaveBeenCalledTimes(1))
    const [terceroId, payload] = vi.mocked(actualizarTercero).mock.calls[0]
    expect(terceroId).toBe('tercero-1')
    expect(payload).toEqual({ email: 'compras@hospital.org' })
    expect(Object.keys(payload).every((campo) => CAMPOS_APP_TERCERO.includes(campo))).toBe(true)
  })

  it('S7: el rol cliente muestra tipo y estado de solo lectura y guarda solo condición y forma de pago', async () => {
    vi.mocked(obtenerRolCliente).mockReset().mockResolvedValue(ROL_CLIENTE)
    renderConQueryClient(<TerceroDetalle terceroId="tercero-1" />)

    const seccion = within(
      (await screen.findByRole('heading', { name: 'Rol cliente' })).closest('section')!,
    )
    await waitFor(() => expect(seccion.getByText('hospital')).toBeInTheDocument())
    expect(seccion.queryByRole('combobox', { name: /tipo/i })).not.toBeInTheDocument()
    expect(seccion.getByText('Activo')).toBeInTheDocument()
    expect(seccion.queryByRole('button', { name: /desactivar rol|reactivar rol/i })).not.toBeInTheDocument()

    await waitFor(() =>
      expect(seccion.getByRole('combobox', { name: /condición de pago/i })).toHaveValue('cp-1'),
    )
    fireEvent.click(seccion.getByRole('button', { name: /^guardar$/i }))

    await waitFor(() => expect(actualizarRolCliente).toHaveBeenCalledTimes(1))
    const [, payload] = vi.mocked(actualizarRolCliente).mock.calls[0]
    expect(payload).toEqual({ condicion_pago_id: 'cp-1', forma_pago_id: 'fp-1' })
    expect(Object.keys(payload).every((campo) => CAMPOS_APP_ROL.includes(campo))).toBe(true)
  })

  it('S7: el rol proveedor muestra tipo y marcas de solo lectura y guarda solo condición y forma de pago', async () => {
    vi.mocked(obtenerRolProveedor).mockReset().mockResolvedValue(ROL_PROVEEDOR)
    renderConQueryClient(<TerceroDetalle terceroId="tercero-1" />)

    const seccion = within(
      (await screen.findByRole('heading', { name: 'Rol proveedor' })).closest('section')!,
    )
    await waitFor(() => expect(seccion.getByText('laboratorio')).toBeInTheDocument())
    expect(seccion.queryByRole('combobox', { name: /tipo/i })).not.toBeInTheDocument()
    expect(seccion.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(seccion.getByText('Es competidor')).toBeInTheDocument()
    expect(seccion.getByText('Es proveedor de compra')).toBeInTheDocument()
    expect(seccion.queryByRole('button', { name: /desactivar rol|reactivar rol/i })).not.toBeInTheDocument()

    await waitFor(() =>
      expect(seccion.getByRole('combobox', { name: /forma de pago/i })).toHaveValue('fp-1'),
    )
    fireEvent.click(seccion.getByRole('button', { name: /^guardar$/i }))

    await waitFor(() => expect(actualizarRolProveedor).toHaveBeenCalledTimes(1))
    const [, payload] = vi.mocked(actualizarRolProveedor).mock.calls[0]
    expect(payload).toEqual({ condicion_pago_id: 'cp-1', forma_pago_id: 'fp-1' })
    expect(Object.keys(payload).every((campo) => CAMPOS_APP_ROL.includes(campo))).toBe(true)
  })
})
