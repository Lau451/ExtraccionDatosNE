import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}))

vi.mock('@/lib/api/presupuestacion', () => {
  class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.status = status
      this.name = 'ApiError'
    }
  }
  return { presupuestacionFetch: vi.fn(), ApiError }
})

import { supabase } from '@/lib/supabase'
import { ApiError, presupuestacionFetch } from '@/lib/api/presupuestacion'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const sesionFalsa = { user: { id: 'user-1' } } as any

function perfilFalso(nombre: string) {
  return {
    id: 'user-1',
    drogueria_id: null,
    rol: 'admin' as const,
    nombre,
    apellido: null,
    es_sistema: false,
    activo: true,
  }
}

function Probe() {
  const { loading, perfilLoading, perfil, refrescarPerfil } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="perfilLoading">{String(perfilLoading)}</span>
      <span data-testid="perfil">{perfil ? perfil.nombre : 'null'}</span>
      <button onClick={() => refrescarPerfil()}>refrescar</button>
    </div>
  )
}

beforeEach(() => {
  vi.mocked(supabase.auth.getSession).mockReset()
  vi.mocked(supabase.auth.signOut).mockClear()
  vi.mocked(presupuestacionFetch).mockReset()
})

describe('AuthProvider', () => {
  it('perfilLoading no se resuelve antes que loading (regresión D-LOGIN-005)', async () => {
    let resolverSesion!: (value: unknown) => void
    const sesionPromise = new Promise((resolve) => {
      resolverSesion = resolve
    })
    vi.mocked(supabase.auth.getSession).mockReturnValue(sesionPromise as never)
    vi.mocked(presupuestacionFetch).mockResolvedValue(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    expect(screen.getByTestId('loading').textContent).toBe('true')
    expect(screen.getByTestId('perfilLoading').textContent).toBe('true')

    await act(async () => {
      resolverSesion({ data: { session: sesionFalsa } })
    })

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(screen.getByTestId('loading').textContent).toBe('false')
    expect(screen.getByTestId('perfil').textContent).toBe('Ana')
  })

  it('llama a signOut automáticamente si el perfil responde 401 (D-LOGIN-006)', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    vi.mocked(presupuestacionFetch).mockRejectedValue(new ApiError('no autorizado', 401))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(supabase.auth.signOut).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('perfil').textContent).toBe('null')
  })

  it('llama a signOut automáticamente si el perfil responde 404 (D-LOGIN-006)', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    vi.mocked(presupuestacionFetch).mockRejectedValue(new ApiError('no encontrado', 404))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(supabase.auth.signOut).toHaveBeenCalledTimes(1))
  })

  it('NO llama a signOut si el error del perfil no es 401/404', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    vi.mocked(presupuestacionFetch).mockRejectedValue(new ApiError('error de servidor', 500))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })

  it('refrescarPerfil() vuelve a pedir el perfil', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    vi.mocked(presupuestacionFetch).mockResolvedValue(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('Ana'))

    vi.mocked(presupuestacionFetch).mockResolvedValue(perfilFalso('Ana renombrada'))

    await act(async () => {
      screen.getByText('refrescar').click()
    })

    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('Ana renombrada'))
  })
})
