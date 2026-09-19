import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ClienteBuscador } from './ClienteBuscador'

vi.mock('@/lib/api/terceros', () => ({
  listarTerceros: vi.fn(),
}))

import { listarTerceros } from '@/lib/api/terceros'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

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

const TERCERO_SOLO_PROVEEDOR = {
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

beforeEach(() => {
  vi.mocked(listarTerceros).mockReset().mockResolvedValue({ items: [], total: 0 })
})

describe('ClienteBuscador (D3.2)', () => {
  it('con q de 1 carácter no dispara ningún request, ni siquiera tras el debounce', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderConQueryClient(<ClienteBuscador onSeleccionar={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText(/buscá por razón social/i), {
      target: { value: 'h' },
    })

    await vi.advanceTimersByTimeAsync(300)

    expect(listarTerceros).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('arranca vacío: no dispara ningún request al montar sin q', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderConQueryClient(<ClienteBuscador onSeleccionar={vi.fn()} />)

    await vi.advanceTimersByTimeAsync(300)

    expect(listarTerceros).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('el debounce de 300ms coalesce las pulsaciones en un solo request con el valor final', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listarTerceros).mockResolvedValue({ items: [TERCERO_CLIENTE], total: 1 })
    renderConQueryClient(<ClienteBuscador onSeleccionar={vi.fn()} />)

    const input = screen.getByPlaceholderText(/buscá por razón social/i)
    fireEvent.change(input, { target: { value: 'h' } })
    fireEvent.change(input, { target: { value: 'ho' } })
    fireEvent.change(input, { target: { value: 'hos' } })
    fireEvent.change(input, { target: { value: 'hospital' } })

    await vi.advanceTimersByTimeAsync(300)

    await waitFor(() => expect(listarTerceros).toHaveBeenCalledTimes(1))
    expect(listarTerceros).toHaveBeenCalledWith(
      expect.objectContaining({ q: 'hospital' }),
    )
    vi.useRealTimers()
  })

  it('la llamada lleva rol: "todos" (nunca "clientes", C7-iii) y filtra en el cliente por tiene_rol_cliente', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(listarTerceros).mockResolvedValue({
      items: [TERCERO_CLIENTE, TERCERO_SOLO_PROVEEDOR],
      total: 2,
    })
    renderConQueryClient(<ClienteBuscador onSeleccionar={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText(/buscá por razón social/i), {
      target: { value: 'hospital' },
    })
    await vi.advanceTimersByTimeAsync(300)

    await waitFor(() =>
      expect(listarTerceros).toHaveBeenCalledWith(
        expect.objectContaining({ rol: 'todos', pageSize: 20 }),
      ),
    )
    expect(listarTerceros).not.toHaveBeenCalledWith(
      expect.objectContaining({ rol: 'clientes' }),
    )

    await waitFor(() => expect(screen.getByText(/hospital central/i)).toBeInTheDocument())
    expect(screen.queryByText(/laboratorio xyz/i)).not.toBeInTheDocument()
    vi.useRealTimers()
  })
})
