import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CrearRenglonDialog } from './CrearRenglonDialog'
import { pcpQueryKeys } from './queryKeys'

vi.mock('@/lib/api/pcp', () => ({ crearRenglon: vi.fn() }))

import { crearRenglon } from '@/lib/api/pcp'

const RENGLON_CREADO = {
  id: 'reng-9', drogueria_id: 'drog-1', pcp_id: 'pcp-1', item_proceso_id: 'item-9',
  producto_id: null, cantidad: null, precio_referencia: null, origen: 'manual' as const,
  regla_pcp_id: null, estado: 'pendiente' as const,
}

function renderDialog(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(<QueryClientProvider client={queryClient}><CrearRenglonDialog pcpId="pcp-1" /></QueryClientProvider>)
  return queryClient
}

beforeEach(() => {
  vi.mocked(crearRenglon).mockReset().mockResolvedValue(RENGLON_CREADO)
})

describe('CrearRenglonDialog', () => {
  it('crea un renglón con el item_proceso_id ingresado y refresca solo la lista de renglones del PCP', async () => {
    const queryClient = renderDialog()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')

    fireEvent.click(screen.getByRole('button', { name: /nuevo renglón/i }))
    fireEvent.change(screen.getByLabelText(/ítem de proceso/i), { target: { value: 'item-9' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))

    await waitFor(() => expect(crearRenglon).toHaveBeenCalledWith('pcp-1', { item_proceso_id: 'item-9' }))
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.renglones('pcp-1') }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /^crear$/i })).not.toBeInTheDocument())
  })

  it('muestra el mensaje de validación del servidor sin cerrar el diálogo', async () => {
    vi.mocked(crearRenglon).mockRejectedValue(Object.assign(new Error('item_proceso_id: Field required'), { status: 422 }))
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: /nuevo renglón/i }))
    fireEvent.change(screen.getByLabelText(/ítem de proceso/i), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('item_proceso_id: Field required')
    expect(screen.getByRole('button', { name: /^crear$/i })).toBeInTheDocument()
  })
})
