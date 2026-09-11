import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PcpDetalle } from './PcpDetalle'
import type { PcpRenglon } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
  Outlet: () => null,
}))
vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({
  obtenerPcp: vi.fn(), listarRenglones: vi.fn(), listarRenglonesSeleccionados: vi.fn(),
  listarSeleccionesAgrupables: vi.fn(), agruparConsultas: vi.fn(),
  cambiarEstadoPcp: vi.fn(), cerrarPcp: vi.fn(), crearRenglon: vi.fn(),
}))

import {
  agruparConsultas, cambiarEstadoPcp, cerrarPcp, crearRenglon, listarRenglones, listarRenglonesSeleccionados,
  listarSeleccionesAgrupables, obtenerPcp,
} from '@/lib/api/pcp'

const PCP_NUEVA = {
  id: 'pcp-1', drogueria_id: 'drog-1', presupuesto_id: 'pres-1', proceso_comercial_id: 'proc-1',
  estado: 'nueva' as const, fecha_entrega_solicitada: null, solicitante_id: null, sector_id: null,
  origen: 'manual' as const, regla_pcp_id: null, notas: null, cerrada_at: null, cerrada_por: null,
}
const RENGLONES: PcpRenglon[] = [
  { id: 'reng-1', drogueria_id: 'drog-1', pcp_id: 'pcp-1', item_proceso_id: 'item-1', producto_id: 'prod-1', cantidad: 2, precio_referencia: null, origen: 'manual', regla_pcp_id: null, estado: 'pendiente' },
  { id: 'reng-2', drogueria_id: 'drog-1', pcp_id: 'pcp-1', item_proceso_id: 'item-2', producto_id: null, cantidad: null, precio_referencia: null, origen: 'manual', regla_pcp_id: null, estado: 'pendiente' },
]

function renderDetalle(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(<QueryClientProvider client={queryClient}><PcpDetalle pcpId="pcp-1" /></QueryClientProvider>)
  return queryClient
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerPcp).mockReset().mockResolvedValue(PCP_NUEVA)
  vi.mocked(listarRenglones).mockReset().mockResolvedValue(RENGLONES)
  vi.mocked(listarRenglonesSeleccionados).mockReset().mockResolvedValue(['reng-1'])
  vi.mocked(listarSeleccionesAgrupables).mockReset().mockResolvedValue([])
  vi.mocked(agruparConsultas).mockReset().mockResolvedValue([])
  vi.mocked(cambiarEstadoPcp).mockReset().mockResolvedValue({ ...PCP_NUEVA, estado: 'en_gestion' })
  vi.mocked(cerrarPcp).mockReset().mockResolvedValue({ ...PCP_NUEVA, estado: 'cerrada', cerrada_at: '2026-09-10', cerrada_por: 'user-1' })
  vi.mocked(crearRenglon).mockReset().mockResolvedValue(RENGLONES[0])
})

describe('PcpDetalle', () => {
  it('shows negotiated and pending renglones, then offers only the next transition', async () => {
    renderDetalle()
    expect(await screen.findByText('Negociado')).toBeInTheDocument()
    expect(screen.getByText('Pendiente')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /avanzar a en gestión/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /esperando respuesta/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /avanzar a en gestión/i }))
    await waitFor(() => expect(cambiarEstadoPcp).toHaveBeenCalledWith('pcp-1', 'en_gestion'))
  })

  it('renders every lifecycle stage and identifies Nueva as the current stage', async () => {
    renderDetalle()

    const stages = within(await screen.findByRole('list', { name: 'Etapas del PCP' }))
    expect(stages.getAllByRole('listitem')).toHaveLength(4)
    expect(stages.getByRole('listitem', { name: 'Nueva — actual' })).toHaveAttribute('aria-current', 'step')
    expect(stages.getByRole('listitem', { name: 'En gestión — pendiente' })).not.toHaveAttribute('aria-current')
    expect(stages.getByRole('listitem', { name: 'Esperando respuesta — pendiente' })).toBeInTheDocument()
    expect(stages.getByRole('listitem', { name: 'Cerrada — pendiente' })).toBeInTheDocument()
  })

  it('distinguishes completed and current stages after a sequential advance', async () => {
    vi.mocked(obtenerPcp).mockResolvedValue({ ...PCP_NUEVA, estado: 'en_gestion' })
    renderDetalle()

    const stages = within(await screen.findByRole('list', { name: 'Etapas del PCP' }))
    expect(stages.getByRole('listitem', { name: 'Nueva — completada' })).toBeInTheDocument()
    expect(stages.getByRole('listitem', { name: 'En gestión — actual' })).toHaveAttribute('aria-current', 'step')
    expect(stages.getByRole('listitem', { name: 'Esperando respuesta — pendiente' })).toBeInTheDocument()
  })

  it('keeps state and close controls absent for a read-only role', async () => {
    perfilMock.rol = 'superadmin'
    renderDetalle()
    await screen.findByRole('heading', { name: /pcp pres-1/i })

    expect(screen.queryByRole('button', { name: /avanzar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cerrar pcp/i })).not.toBeInTheDocument()
  })

  it('renders loading and error feedback for the PCP detail requests', async () => {
    vi.mocked(obtenerPcp).mockImplementation(() => new Promise(() => undefined))
    renderDetalle()
    expect(screen.getByText(/cargando pcp/i)).toBeInTheDocument()

    vi.mocked(obtenerPcp).mockReset().mockRejectedValue(new Error('sin conexión'))
    renderDetalle()
    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo cargar el detalle/i)
  })

  it('merges close results into detail and every list cache without a blanket PCP refetch', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(pcpQueryKeys.lista(), [PCP_NUEVA])
    queryClient.setQueryData(pcpQueryKeys.lista({ estado: 'nueva' }), [PCP_NUEVA])
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    renderDetalle(queryClient)
    fireEvent.click(await screen.findByRole('button', { name: /cerrar pcp/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar cierre/i }))

    await waitFor(() => expect(cerrarPcp).toHaveBeenCalledWith('pcp-1'))
    const cerrado = await waitFor(() => queryClient.getQueryData<typeof PCP_NUEVA>(pcpQueryKeys.detalle('pcp-1')))
    expect(cerrado?.estado).toBe('cerrada')
    expect(queryClient.getQueryData<typeof PCP_NUEVA[]>(pcpQueryKeys.lista())?.[0].estado).toBe('cerrada')
    expect(queryClient.getQueryData<typeof PCP_NUEVA[]>(pcpQueryKeys.lista({ estado: 'nueva' }))?.[0].estado).toBe('cerrada')
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.renglones('pcp-1'), refetchType: 'none' })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['pcp', 'sugerencias'] })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: pcpQueryKeys.listas() })
  })

  it('merges a state-transition result into every list cache, not just the detail', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(pcpQueryKeys.lista(), [PCP_NUEVA])
    queryClient.setQueryData(pcpQueryKeys.lista({ estado: 'nueva' }), [PCP_NUEVA])
    renderDetalle(queryClient)

    fireEvent.click(await screen.findByRole('button', { name: /avanzar a en gestión/i }))
    await waitFor(() => expect(cambiarEstadoPcp).toHaveBeenCalledWith('pcp-1', 'en_gestion'))

    await waitFor(() => {
      expect(queryClient.getQueryData<typeof PCP_NUEVA[]>(pcpQueryKeys.lista())?.[0].estado).toBe('en_gestion')
    })
    expect(queryClient.getQueryData<typeof PCP_NUEVA[]>(pcpQueryKeys.lista({ estado: 'nueva' }))?.[0].estado).toBe('en_gestion')
  })

  it('lets a write-role user create a renglón and refreshes only the renglones list', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    renderDetalle(queryClient)
    await screen.findByText('Negociado')

    fireEvent.click(screen.getByRole('button', { name: /nuevo renglón/i }))
    fireEvent.change(screen.getByLabelText(/ítem de proceso/i), { target: { value: 'item-9' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))

    await waitFor(() => expect(crearRenglon).toHaveBeenCalledWith('pcp-1', { item_proceso_id: 'item-9' }))
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.renglones('pcp-1') })
  })

  it('hides the create-renglón control for a read-only role', async () => {
    perfilMock.rol = 'superadmin'
    renderDetalle()
    await screen.findByText('Negociado')

    expect(screen.queryByRole('button', { name: /nuevo renglón/i })).not.toBeInTheDocument()
  })

  it('lets a write-role user group agrupable selections spanning two renglones on the same proveedor into one consultation call', async () => {
    vi.mocked(listarSeleccionesAgrupables).mockResolvedValue([
      { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
      { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
    ])
    renderDetalle()
    await screen.findByText('Negociado')

    fireEvent.click(await screen.findByRole('button', { name: /agrupar consulta/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar/i }))

    await waitFor(() => expect(agruparConsultas).toHaveBeenCalledWith({
      selecciones: [
        { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
        { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
      ],
    }))
  })

  it('hides the grouping trigger when the PCP has no agrupable selections', async () => {
    renderDetalle()
    await screen.findByText('Negociado')

    expect(screen.queryByRole('button', { name: /agrupar consulta/i })).not.toBeInTheDocument()
  })

  it('hides the grouping trigger for a read-only role even with agrupable selections', async () => {
    vi.mocked(listarSeleccionesAgrupables).mockResolvedValue([
      { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
    ])
    perfilMock.rol = 'superadmin'
    renderDetalle()
    await screen.findByText('Negociado')

    expect(screen.queryByRole('button', { name: /agrupar consulta/i })).not.toBeInTheDocument()
  })
})
