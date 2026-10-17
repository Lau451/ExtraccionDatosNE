import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompromisoEntrega } from '@/lib/api/compromisos'
import { ApiError } from '@/lib/api/presupuestacion'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, params }: { children?: React.ReactNode; to: string; params?: Record<string, string> }) => (
    <a href={to.replace('$ordenCompraId', params?.ordenCompraId ?? '')}>{children}</a>
  ),
}))
vi.mock('@/lib/api/compromisos', () => ({ listarCompromisos: vi.fn() }))

import { listarCompromisos } from '@/lib/api/compromisos'
import { VistaLista } from './VistaLista'

function renderVista(filtro = '') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <VistaLista filtro={filtro} />
    </QueryClientProvider>,
  )
}

function fila(o: Partial<CompromisoEntrega> = {}): CompromisoEntrega {
  return {
    drogueria_id: 'd1',
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-100',
    version_numero: 1,
    exportado_at: '2026-10-01T10:00:00Z',
    cliente: 'Hospital Norte',
    entrega_oc_id: 'e-1',
    numero_entrega: 1,
    fecha_entrega_planificada: '2026-11-05',
    numero_renglon: 1,
    codigo_articulo: 'A1',
    descripcion: 'Ibuprofeno 400mg',
    cantidad_planificada: 10,
    situacion: 'futura',
    dias_atraso: 0,
    posicion_en_plan: 1,
    entregas_en_plan: 1,
    ...o,
  }
}

describe('VistaLista', () => {
  beforeEach(() => {
    vi.mocked(listarCompromisos).mockReset()
  })

  it('muestra estado de carga', () => {
    vi.mocked(listarCompromisos).mockReturnValue(new Promise(() => {}))
    renderVista()
    expect(screen.getByText(/Cargando compromisos/)).toBeTruthy()
  })

  it('muestra mensaje vacío', async () => {
    vi.mocked(listarCompromisos).mockResolvedValue([])
    renderVista()
    expect(await screen.findByText(/No hay entregas comprometidas/)).toBeTruthy()
  })

  it('muestra el mensaje del backend ante un error', async () => {
    vi.mocked(listarCompromisos).mockRejectedValue(new ApiError('Rol sin permiso', 403))
    renderVista()
    expect(await screen.findByText(/Rol sin permiso/)).toBeTruthy()
  })

  it('muestra vencidas con días de atraso y futuras agrupadas por mes y fecha (es-AR)', async () => {
    vi.mocked(listarCompromisos).mockResolvedValue([
      fila({ entrega_oc_id: 'e-v', numero_oc: 'OC-7', descripcion: 'Amoxicilina', situacion: 'vencida', dias_atraso: 3, fecha_entrega_planificada: '2026-10-08' }),
      fila({ cantidad_planificada: 10 }),
      fila({ numero_renglon: 2, descripcion: 'Paracetamol', cantidad_planificada: 4 }),
    ])
    renderVista()

    expect(await screen.findByText('Vencidas sin confirmar')).toBeTruthy()
    expect(screen.getByText(/3 días de atraso/)).toBeTruthy()
    expect(screen.getByText(/noviembre de 2026/i)).toBeTruthy()
    expect(screen.getByText(/05\/11\/2026/)).toBeTruthy()
    expect(screen.getByText('Ibuprofeno 400mg')).toBeTruthy()
    expect(screen.getByText('Paracetamol')).toBeTruthy()
    expect(screen.getAllByText('Hospital Norte').length).toBeGreaterThan(0)
    const link = screen.getByRole('link', { name: 'OC-100' })
    expect(link.getAttribute('href')).toBe('/ordenes-compra/oc-1')
  })

  it('filtra por cliente u OC', async () => {
    vi.mocked(listarCompromisos).mockResolvedValue([
      fila({ entrega_oc_id: 'e-1', cliente: 'Hospital Norte', descripcion: 'Ibuprofeno' }),
      fila({ entrega_oc_id: 'e-2', cliente: 'Clínica Sur', numero_oc: 'OC-200', descripcion: 'Paracetamol' }),
    ])
    renderVista('clinica')

    expect(await screen.findByText('Paracetamol')).toBeTruthy()
    expect(screen.queryByText('Ibuprofeno')).toBeNull()
  })
})
