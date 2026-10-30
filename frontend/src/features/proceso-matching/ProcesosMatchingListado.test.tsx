import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProcesosMatchingListado } from './ProcesosMatchingListado'

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children?: React.ReactNode
    to: string
    params: { procesoId: string }
  }) => <a href={to.replace('$procesoId', params.procesoId)}>{children}</a>,
}))

vi.mock('@/lib/api/matching', () => ({
  listarProcesosConMatchingPendiente: vi.fn(),
}))

import { listarProcesosConMatchingPendiente } from '@/lib/api/matching'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.mocked(listarProcesosConMatchingPendiente).mockReset()
})

describe('ProcesosMatchingListado', () => {
  it('lists each proceso with unresolved renglones and links to its matching screen', async () => {
    vi.mocked(listarProcesosConMatchingPendiente).mockResolvedValue([
      {
        proceso_comercial_id: 'proc-1',
        proceso: 'HOSPITAL SAN JOSE - LICITACION ACELERADA 16/26',
        clase: 'licitacion',
        cliente: 'Hospital San José',
        pendientes: 3,
        sugeridos: 1,
      },
      {
        proceso_comercial_id: 'proc-2',
        proceso: 'Clínica Norte - 4',
        clase: 'cotizacion',
        cliente: 'Clínica Norte',
        pendientes: 0,
        sugeridos: 2,
      },
    ])

    renderConQueryClient(<ProcesosMatchingListado />)

    const enlace = await screen.findByRole('link', { name: 'HOSPITAL SAN JOSE - LICITACION ACELERADA 16/26' })
    expect(enlace.getAttribute('href')).toBe('/procesos-comerciales/proc-1/matching')
    expect(screen.getByText('Hospital San José · Licitación')).toBeInTheDocument()
    expect(screen.getByText('3 pendientes · 1 sugerido')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Clínica Norte - 4' }).getAttribute('href')).toBe(
      '/procesos-comerciales/proc-2/matching',
    )
    expect(screen.getByText('Clínica Norte · Directa')).toBeInTheDocument()
    expect(screen.getByText('0 pendientes · 2 sugeridos')).toBeInTheDocument()
  })

  it('says when there is nothing left to match', async () => {
    vi.mocked(listarProcesosConMatchingPendiente).mockResolvedValue([])

    renderConQueryClient(<ProcesosMatchingListado />)

    expect(await screen.findByText('No hay procesos con renglones sin resolver.')).toBeInTheDocument()
  })

  it('shows the load error', async () => {
    vi.mocked(listarProcesosConMatchingPendiente).mockRejectedValue(new Error('Error 500 al llamar /matching/procesos'))

    renderConQueryClient(<ProcesosMatchingListado />)

    expect(await screen.findByText('Error 500 al llamar /matching/procesos')).toBeInTheDocument()
  })
})
