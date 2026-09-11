import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GestionPcp } from './GestionPcp'

const { navigateMock, perfilMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  perfilMock: { rol: 'admin' as string },
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
  useNavigate: () => navigateMock,
}))
vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({
  listarPcp: vi.fn(),
  listarPresupuestosElegibles: vi.fn(),
  crearPcp: vi.fn(),
}))

import { crearPcp, listarPcp, listarPresupuestosElegibles } from '@/lib/api/pcp'

const PCP_NUEVA = {
  id: 'pcp-1', drogueria_id: 'drog-1', presupuesto_id: 'pres-1', proceso_comercial_id: 'proc-1',
  estado: 'nueva' as const, fecha_entrega_solicitada: null, solicitante_id: null, sector_id: null,
  origen: 'manual' as const, regla_pcp_id: null, notas: null, cerrada_at: null, cerrada_por: null,
}
const PCP_GESTION = { ...PCP_NUEVA, id: 'pcp-2', presupuesto_id: 'pres-2', estado: 'en_gestion' as const }

function renderGestion() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><GestionPcp /></QueryClientProvider>)
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  navigateMock.mockReset()
  vi.mocked(listarPcp).mockReset().mockResolvedValue([PCP_NUEVA, PCP_GESTION])
  vi.mocked(listarPresupuestosElegibles).mockReset().mockResolvedValue([
    { id: 'pres-elegible', nombre: 'Hospital Central' },
  ])
  vi.mocked(crearPcp).mockReset().mockResolvedValue(PCP_NUEVA)
})

describe('GestionPcp', () => {
  it('filtra por estado y crea un PCP para llevar al detalle', async () => {
    renderGestion()
    await waitFor(() => expect(screen.getByText('pres-1')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText(/estado/i), { target: { value: 'en_gestion' } })
    await waitFor(() => expect(listarPcp).toHaveBeenLastCalledWith({ estado: 'en_gestion' }))
    await waitFor(() => expect(screen.getByText('pres-2')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /nuevo pcp/i }))
    expect(await screen.findByRole('option', { name: /hospital central/i })).toHaveValue('pres-elegible')
    fireEvent.change(screen.getByLabelText(/presupuesto elegible/i), { target: { value: 'pres-elegible' } })
    fireEvent.click(screen.getByRole('button', { name: /^crear$/i }))
    await waitFor(() => expect(crearPcp).toHaveBeenCalledWith({ presupuesto_id: 'pres-elegible' }))
    expect(navigateMock).toHaveBeenCalledWith({ to: '/pcp/$pcpId', params: { pcpId: 'pcp-1' } })
  })

  it('no permite enviar un identificador que no está entre los presupuestos elegibles', async () => {
    renderGestion()
    fireEvent.click(await screen.findByRole('button', { name: /nuevo pcp/i }))
    await screen.findByRole('option', { name: /hospital central/i })

    fireEvent.change(screen.getByLabelText(/presupuesto elegible/i), { target: { value: 'pres-arbitrario' } })
    const crear = screen.getByRole('button', { name: /^crear$/i })

    expect(crear).toBeDisabled()
    fireEvent.click(crear)
    expect(crearPcp).not.toHaveBeenCalled()
  })

  it('muestra el vacío y omite el alta para el rol de solo lectura', async () => {
    perfilMock.rol = 'superadmin'
    vi.mocked(listarPcp).mockResolvedValue([])
    renderGestion()

    await waitFor(() => expect(screen.getByText(/no hay pcp/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /nuevo pcp/i })).not.toBeInTheDocument()
  })
})
