import { act, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      setSession: vi.fn(),
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

vi.mock('@/lib/api/auth', () => ({ iniciarSesion: vi.fn() }))

import { supabase } from '@/lib/supabase'
import { ApiError, presupuestacionFetch } from '@/lib/api/presupuestacion'
import { iniciarSesion } from '@/lib/api/auth'

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
    username: 'ana',
    debe_cambiar_password: false,
  }
}

const CAPACIDADES_ADMIN = ['extraccion.extraer', 'usuarios.gestionar']

// GET /usuarios/{id} devuelve el perfil y GET /auth/capacidades la lista del rol
// (spec S7); `capacidades` puede ser un error para simular el 403 de L5.
function responder(perfil: unknown, capacidades: string[] | Error = CAPACIDADES_ADMIN) {
  vi.mocked(presupuestacionFetch).mockImplementation(async (path: string) => {
    if (path === '/auth/capacidades') {
      if (capacidades instanceof Error) throw capacidades
      return { rol: 'admin', capacidades }
    }
    return perfil
  })
}

function SignInProbe() {
  const { signIn, perfil } = useAuth()
  const [estado, setEstado] = useState('idle')
  return (
    <div>
      <span data-testid="estado">{estado}</span>
      <span data-testid="perfil">{perfil ? perfil.nombre : 'null'}</span>
      <button
        onClick={() =>
          signIn('jperez', 'secreta123').then(
            () => setEstado('ok'),
            (error: Error) => setEstado(`error:${error.message}`),
          )
        }
      >
        entrar
      </button>
    </div>
  )
}

function Probe() {
  const { loading, perfilLoading, perfil, refrescarPerfil, capacidades, puede, errorCapacidades } = useAuth()
  const [refrescadas, setRefrescadas] = useState('')
  return (
    <div>
      <span data-testid="capacidades">{capacidades.join(',')}</span>
      <span data-testid="errorCapacidades">{errorCapacidades ?? 'null'}</span>
      <span data-testid="puedeUsuarios">{String(puede('usuarios.gestionar'))}</span>
      <span data-testid="refrescadas">{refrescadas}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="perfilLoading">{String(perfilLoading)}</span>
      <span data-testid="perfil">{perfil ? perfil.nombre : 'null'}</span>
      <button onClick={() => refrescarPerfil().then((caps) => setRefrescadas(caps.join(',')))}>refrescar</button>
    </div>
  )
}

beforeEach(() => {
  vi.mocked(supabase.auth.getSession).mockReset()
  vi.mocked(supabase.auth.signOut).mockClear()
  vi.mocked(presupuestacionFetch).mockReset()
  vi.mocked(supabase.auth.setSession).mockReset()
  vi.mocked(iniciarSesion).mockReset()
})

describe('signIn con username (S1)', () => {
  const login = {
    access_token: 'acc',
    refresh_token: 'ref',
    expires_in: 3600,
    expires_at: 123,
    token_type: 'bearer',
    user: { id: 'user-1' },
  }

  it('llama a /auth/login, instala la sesión con setSession y espera el perfil antes de resolver', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null } } as never)
    vi.mocked(iniciarSesion).mockResolvedValue(login)
    vi.mocked(supabase.auth.setSession).mockResolvedValue({ data: {}, error: null } as never)
    responder(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <SignInProbe />
      </AuthProvider>,
    )

    await act(async () => {
      screen.getByText('entrar').click()
    })

    await waitFor(() => expect(screen.getByTestId('estado').textContent).toBe('ok'))
    expect(iniciarSesion).toHaveBeenCalledWith('jperez', 'secreta123')
    expect(supabase.auth.setSession).toHaveBeenCalledWith({ access_token: 'acc', refresh_token: 'ref' })
    expect(presupuestacionFetch).toHaveBeenCalledWith('/usuarios/user-1')
    expect(screen.getByTestId('perfil').textContent).toBe('Ana')
  })

  it('propaga el error del login y no instala sesión', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: null } } as never)
    vi.mocked(iniciarSesion).mockRejectedValue(new ApiError('Usuario o contraseña incorrectos', 401))

    render(
      <AuthProvider>
        <SignInProbe />
      </AuthProvider>,
    )

    await act(async () => {
      screen.getByText('entrar').click()
    })

    await waitFor(() =>
      expect(screen.getByTestId('estado').textContent).toBe('error:Usuario o contraseña incorrectos'),
    )
    expect(supabase.auth.setSession).not.toHaveBeenCalled()
    expect(presupuestacionFetch).not.toHaveBeenCalled()
  })
})

describe('AuthProvider', () => {
  it('perfilLoading no se resuelve antes que loading (regresión D-LOGIN-005)', async () => {
    let resolverSesion!: (value: unknown) => void
    const sesionPromise = new Promise((resolve) => {
      resolverSesion = resolve
    })
    vi.mocked(supabase.auth.getSession).mockReturnValue(sesionPromise as never)
    responder(perfilFalso('Ana'))

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

  it('un refresh de token del mismo usuario no recarga el perfil ni tira perfilLoading a true', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('Ana'))
    // Perfil + capacidades.
    expect(presupuestacionFetch).toHaveBeenCalledTimes(2)

    // Supabase dispara onAuthStateChange con un objeto session NUEVO pero el
    // MISMO user.id cada vez que la pestaña recupera el foco y refresca el
    // token. Antes del fix esto recargaba el perfil entero (perfilLoading
    // pasaba a true) y con eso tiraba abajo toda la app en main.tsx.
    const onAuthStateChangeCallback = vi.mocked(supabase.auth.onAuthStateChange).mock.calls[0][0]
    const sesionRefrescada = { user: { id: 'user-1' } } as never

    await act(async () => {
      onAuthStateChangeCallback('TOKEN_REFRESHED' as never, sesionRefrescada)
    })

    expect(screen.getByTestId('perfilLoading').textContent).toBe('false')
    expect(presupuestacionFetch).toHaveBeenCalledTimes(2)
  })

  it('refrescarPerfil() vuelve a pedir el perfil', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('Ana'))

    responder(perfilFalso('Ana renombrada'), ['extraccion.extraer', 'usuarios.gestionar', 'pcp.leer'])

    await act(async () => {
      screen.getByText('refrescar').click()
    })

    await waitFor(() => expect(screen.getByTestId('perfil').textContent).toBe('Ana renombrada'))
    // S7/L5: refrescarPerfil también recarga las capacidades y las devuelve.
    expect(screen.getByTestId('capacidades').textContent).toBe('extraccion.extraer,usuarios.gestionar,pcp.leer')
    expect(screen.getByTestId('refrescadas').textContent).toBe('extraccion.extraer,usuarios.gestionar,pcp.leer')
  })

  it('S7: carga las capacidades junto con el perfil y las expone con puede()', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder(perfilFalso('Ana'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(presupuestacionFetch).toHaveBeenCalledWith('/auth/capacidades')
    expect(screen.getByTestId('capacidades').textContent).toBe('extraccion.extraer,usuarios.gestionar')
    expect(screen.getByTestId('puedeUsuarios').textContent).toBe('true')
  })

  it('S7/L5: un 403 de capacidades (contraseña temporal) deja la lista vacía y no cierra la sesión', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder({ ...perfilFalso('Ana'), debe_cambiar_password: true }, new ApiError('Debés cambiar la contraseña', 403))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(screen.getByTestId('perfil').textContent).toBe('Ana')
    expect(screen.getByTestId('capacidades').textContent).toBe('')
    expect(screen.getByTestId('puedeUsuarios').textContent).toBe('false')
    expect(screen.getByTestId('errorCapacidades').textContent).toBe('null')
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })

  it('un fallo de capacidades que no es 403 queda expuesto, no cierra la sesión y refrescarPerfil lo limpia', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder(perfilFalso('Ana'), new ApiError('Error interno', 500))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(screen.getByTestId('perfil').textContent).toBe('Ana')
    expect(screen.getByTestId('capacidades').textContent).toBe('')
    expect(screen.getByTestId('errorCapacidades').textContent).toBe(
      'No se pudieron cargar los permisos de tu usuario (Error interno).',
    )
    expect(supabase.auth.signOut).not.toHaveBeenCalled()

    responder(perfilFalso('Ana'))
    await act(async () => {
      screen.getByText('refrescar').click()
    })

    await waitFor(() => expect(screen.getByTestId('errorCapacidades').textContent).toBe('null'))
    expect(screen.getByTestId('capacidades').textContent).toBe('extraccion.extraer,usuarios.gestionar')
  })

  it('un fallo de red al pedir capacidades también queda expuesto', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({ data: { session: sesionFalsa } } as never)
    responder(perfilFalso('Ana'), new TypeError('Failed to fetch'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('perfilLoading').textContent).toBe('false'))
    expect(screen.getByTestId('errorCapacidades').textContent).toBe(
      'No se pudieron cargar los permisos de tu usuario (Failed to fetch).',
    )
    expect(supabase.auth.signOut).not.toHaveBeenCalled()
  })
})
