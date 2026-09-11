import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SugerenciasPanel } from './SugerenciasPanel'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'compras' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({
  obtenerSugerenciaAgrupacion: vi.fn(),
  listarSugerenciasPreciosRecientes: vi.fn(),
}))

import { obtenerSugerenciaAgrupacion, listarSugerenciasPreciosRecientes } from '@/lib/api/pcp'

const SUGERENCIA_AGRUPACION = {
  producto_id: 'prod-1',
  cantidad_agregada: 36,
  pcp_ids: ['pcp-1', 'pcp-2'],
  renglon_ids: ['reng-1', 'reng-2'],
}

const SUGERENCIA_PRECIO_RECIENTE = {
  precio_proveedor_id: 'precio-1',
  proveedor: 'Droguería Norte',
  mantenimiento_hasta: '2026-12-31',
  dias_restantes: 45,
  precio_unitario: 1500,
  cantidad_minima: 10,
  cantidad_maxima: 100,
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <SugerenciasPanel renglonId="reng-1" />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  perfilMock.rol = 'compras'
  vi.mocked(obtenerSugerenciaAgrupacion).mockReset().mockResolvedValue(null)
  vi.mocked(listarSugerenciasPreciosRecientes).mockReset().mockResolvedValue([])
})

describe('SugerenciasPanel', () => {
  it('muestra la sugerencia de agrupación por cantidad con la cantidad agregada', async () => {
    vi.mocked(obtenerSugerenciaAgrupacion).mockResolvedValue(SUGERENCIA_AGRUPACION as never)

    renderPanel()

    expect(await screen.findByRole('heading', { name: /sugerencia de agrupación/i })).toBeInTheDocument()
    expect(screen.getByText('36')).toBeInTheDocument()
    expect(screen.getByText(/prod-1/)).toBeInTheDocument()
  })

  it('muestra la sugerencia de precio reciente con proveedor, vigencia y banda de cantidad', async () => {
    vi.mocked(listarSugerenciasPreciosRecientes).mockResolvedValue([SUGERENCIA_PRECIO_RECIENTE as never])

    renderPanel()

    expect(await screen.findByRole('heading', { name: /precio reciente/i })).toBeInTheDocument()
    expect(screen.getByText('Droguería Norte')).toBeInTheDocument()
    expect(screen.getByText(/2026-12-31/)).toBeInTheDocument()
    expect(screen.getByText(/10/)).toBeInTheDocument()
    expect(screen.getByText(/100/)).toBeInTheDocument()
    expect(screen.getByText(/1500/)).toBeInTheDocument()
  })

  it('muestra un estado vacío explícito cuando no hay ninguna sugerencia', async () => {
    renderPanel()

    expect(await screen.findByText('No hay sugerencias disponibles para este renglón.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /sugerencia de agrupación/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /precio reciente/i })).not.toBeInTheDocument()
  })

  it.each(['superadmin', 'admin', 'gerencia', 'compras'])(
    'renderiza el panel para el rol de lectura %s sin exigir rol de escritura',
    async (rol) => {
      perfilMock.rol = rol

      renderPanel()

      expect(await screen.findByRole('region', { name: /sugerencias/i })).toBeInTheDocument()
    },
  )

  it('no expone ningún control que mute datos de PCP', async () => {
    vi.mocked(obtenerSugerenciaAgrupacion).mockResolvedValue(SUGERENCIA_AGRUPACION as never)
    vi.mocked(listarSugerenciasPreciosRecientes).mockResolvedValue([SUGERENCIA_PRECIO_RECIENTE as never])

    renderPanel()

    await screen.findByRole('heading', { name: /sugerencia de agrupación/i })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('muestra varias sugerencias de precio reciente como una lista, cada una con su detalle completo', async () => {
    const segundoPrecio = {
      precio_proveedor_id: 'precio-2',
      proveedor: 'Farmacéutica Sur',
      mantenimiento_hasta: '2026-11-15',
      dias_restantes: 20,
      precio_unitario: 980,
      cantidad_minima: 5,
      cantidad_maxima: 50,
    }
    vi.mocked(listarSugerenciasPreciosRecientes).mockResolvedValue([
      SUGERENCIA_PRECIO_RECIENTE,
      segundoPrecio,
    ] as never)

    renderPanel()

    await screen.findByRole('heading', { name: /precio reciente/i })
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Droguería Norte')).toBeInTheDocument()
    expect(screen.getByText('Farmacéutica Sur')).toBeInTheDocument()
    expect(screen.getByText(/2026-12-31/)).toBeInTheDocument()
    expect(screen.getByText(/2026-11-15/)).toBeInTheDocument()
    expect(screen.getByText(/1500/)).toBeInTheDocument()
    expect(screen.getByText(/980/)).toBeInTheDocument()
  })

  it('muestra la cantidad de renglones agrupados cuando la agrupación abarca varios renglones abiertos', async () => {
    const agrupacionVariosRenglones = {
      producto_id: 'prod-9',
      cantidad_agregada: 120,
      pcp_ids: ['pcp-1', 'pcp-2', 'pcp-3'],
      renglon_ids: ['reng-1', 'reng-2', 'reng-3', 'reng-4'],
    }
    vi.mocked(obtenerSugerenciaAgrupacion).mockResolvedValue(agrupacionVariosRenglones as never)

    renderPanel()

    await screen.findByRole('heading', { name: /sugerencia de agrupación/i })
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText(/4 renglones agrupados/i)).toBeInTheDocument()
    expect(screen.getByText(/3 pcps/i)).toBeInTheDocument()
  })
})
