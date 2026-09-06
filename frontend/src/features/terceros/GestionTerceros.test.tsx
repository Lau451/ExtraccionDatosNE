import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GestionTerceros } from './GestionTerceros'

const { perfilMock } = vi.hoisted(() => ({
  perfilMock: { id: 'user-1', rol: 'admin' as string },
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
}))

vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: perfilMock }),
}))

vi.mock('@/lib/api/terceros', () => ({
  listarTerceros: vi.fn(),
  crearTercero: vi.fn(),
  actualizarTercero: vi.fn(),
}))

vi.mock('@/lib/api/catalogosComerciales', () => ({
  listarSectoresContacto: vi.fn().mockResolvedValue([]),
  crearSectorContacto: vi.fn(),
  actualizarSectorContacto: vi.fn(),
  listarCondicionesPago: vi.fn().mockResolvedValue([]),
  crearCondicionPago: vi.fn(),
  actualizarCondicionPago: vi.fn(),
  listarFormasPago: vi.fn().mockResolvedValue([]),
  crearFormaPago: vi.fn(),
  actualizarFormaPago: vi.fn(),
}))

import { crearTercero, listarTerceros } from '@/lib/api/terceros'

const TERCERO_CLIENTE = {
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
  tiene_rol_cliente: true,
  tiene_rol_proveedor: false,
}

const TERCERO_PROVEEDOR = {
  id: 'tercero-2',
  drogueria_id: 'drog-1',
  codigo_interno: 'T002',
  razon_social: 'Laboratorio XYZ',
  nombre_fantasia: null,
  cuit: '30-22222222-2',
  email: null,
  telefono: null,
  sitio_web: null,
  notas: null,
  activo: true,
  tiene_rol_cliente: false,
  tiene_rol_proveedor: true,
}

const TERCERO_AMBOS = {
  id: 'tercero-3',
  drogueria_id: 'drog-1',
  codigo_interno: 'T003',
  razon_social: 'Droguería Mixta',
  nombre_fantasia: null,
  cuit: '30-33333333-3',
  email: null,
  telefono: null,
  sitio_web: null,
  notas: null,
  activo: true,
  tiene_rol_cliente: true,
  tiene_rol_proveedor: true,
}

const TERCERO_SIN_ROL = {
  id: 'tercero-4',
  drogueria_id: 'drog-1',
  codigo_interno: 'T004',
  razon_social: 'Tercero Nuevo',
  nombre_fantasia: null,
  cuit: '30-44444444-4',
  email: null,
  telefono: null,
  sitio_web: null,
  notas: null,
  activo: true,
  tiene_rol_cliente: false,
  tiene_rol_proveedor: false,
}

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(listarTerceros)
    .mockReset()
    .mockResolvedValue([TERCERO_CLIENTE, TERCERO_PROVEEDOR, TERCERO_AMBOS, TERCERO_SIN_ROL])
  vi.mocked(crearTercero).mockReset().mockResolvedValue(TERCERO_SIN_ROL)
})

describe('GestionTerceros', () => {
  it('renderiza el listado con los distintos badges de rol', async () => {
    renderConQueryClient(<GestionTerceros />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())

    const tabla = within(screen.getByRole('table'))
    expect(tabla.getByText('Cliente')).toBeInTheDocument()
    expect(tabla.getByText('Proveedor')).toBeInTheDocument()
    expect(tabla.getByText('Ambos')).toBeInTheDocument()
    expect(tabla.getByText('Sin rol')).toBeInTheDocument()
  })

  it('el filtro de rol "Solo clientes" deja solo los terceros con rol cliente exclusivo', async () => {
    renderConQueryClient(<GestionTerceros />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())

    fireEvent.change(screen.getByDisplayValue('Todos'), { target: { value: 'clientes' } })

    expect(screen.getByText('Hospital Central')).toBeInTheDocument()
    expect(screen.queryByText('Laboratorio XYZ')).not.toBeInTheDocument()
    expect(screen.queryByText('Droguería Mixta')).not.toBeInTheDocument()
    expect(screen.queryByText('Tercero Nuevo')).not.toBeInTheDocument()
  })

  it('el diálogo de alta llama a crearTercero con los campos cargados', async () => {
    renderConQueryClient(<GestionTerceros />)

    await waitFor(() => expect(screen.getByText('Hospital Central')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /nuevo tercero/i }))
    fireEvent.change(screen.getByLabelText(/razón social/i), { target: { value: 'Nueva Farmacia SA' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))

    await waitFor(() =>
      expect(crearTercero).toHaveBeenCalledWith(
        expect.objectContaining({ razon_social: 'Nueva Farmacia SA' }),
      ),
    )
  })
})
