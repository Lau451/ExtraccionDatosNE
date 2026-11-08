import { describe, expect, it } from 'vitest'
import { destinoRedirect } from '@/test/capacidades'
import type { Rol } from './AuthContext'
import type { Capacidad } from './capacidades'
import { homeForRol, requireAuth, requireCapacidad, requireSession } from './routeGuards'

function args(
  auth: { isAuthenticated: boolean; perfil: { rol: Rol; debe_cambiar_password?: boolean } | null },
  capacidades: Capacidad[] = [],
) {
  return { context: { auth: { ...auth, capacidades } }, location: { href: '/admin/usuarios' } }
}

describe('requireAuth', () => {
  it('redirige a /login si no hay sesión', () => {
    expect(() => requireAuth(args({ isAuthenticated: false, perfil: null }))).toThrow()
  })

  it('no hace nada si hay sesión', () => {
    expect(() => requireAuth(args({ isAuthenticated: true, perfil: null }))).not.toThrow()
  })
})

describe('requireCapacidad (S7)', () => {
  const guard = requireCapacidad('usuarios.gestionar')

  it('redirige si el perfil todavía no resolvió (caso D-LOGIN-005/007)', () => {
    expect(() => guard(args({ isAuthenticated: true, perfil: null }, ['usuarios.gestionar']))).toThrow()
  })

  it('redirige si el usuario no tiene la capacidad', () => {
    expect(() =>
      guard(args({ isAuthenticated: true, perfil: { rol: 'comercial' } }, ['extraccion.extraer'])),
    ).toThrow()
  })

  it('deja pasar si el usuario tiene la capacidad', () => {
    expect(() =>
      guard(args({ isAuthenticated: true, perfil: { rol: 'admin' } }, ['usuarios.gestionar'])),
    ).not.toThrow()
  })

  it('decide por la capacidad, no por el rol', () => {
    expect(() => guard(args({ isAuthenticated: true, perfil: { rol: 'admin' } }, []))).toThrow()
  })

  it('redirige a /login antes de evaluar la capacidad si no hay sesión', () => {
    expect(destinoRedirect(() => guard(args({ isAuthenticated: false, perfil: null })))).toBe('/login')
  })
})

describe('homeForRol (S9: aterrizaje sin loop)', () => {
  it.each(['admin', 'gerencia', 'lider_comercial', 'comercial'] as const)(
    '%s con extraccion.extraer aterriza en / (carga)',
    (rol) => {
      expect(homeForRol(rol, ['extraccion.extraer'])).toBe('/')
    },
  )

  it('compras aterriza en /productos y superadmin en /superadmin/empresas', () => {
    expect(homeForRol('compras', ['productos.leer'])).toBe('/productos')
    expect(homeForRol('superadmin', ['droguerias.gestionar'])).toBe('/superadmin/empresas')
  })

  it('sin extraccion.extraer ni rol con home propio va a /mi-cuenta', () => {
    expect(homeForRol('admin', [])).toBe('/mi-cuenta')
    expect(homeForRol(undefined, ['extraccion.extraer'])).toBe('/mi-cuenta')
  })

  it('sin capacidades cargadas no aterriza en una ruta que las pide (sin loop)', () => {
    expect(homeForRol('compras', [])).toBe('/mi-cuenta')
    expect(homeForRol('superadmin', [])).toBe('/mi-cuenta')
  })

  it('un usuario sin la capacidad es redirigido a su home, no a /', () => {
    const guard = requireCapacidad('usuarios.gestionar')
    expect(
      destinoRedirect(() => guard(args({ isAuthenticated: true, perfil: { rol: 'compras' } }, ['productos.leer']))),
    ).toBe('/productos')
  })

  it('sigue redirigiendo a / a un usuario de carga sin la capacidad (comportamiento previo)', () => {
    const guard = requireCapacidad('usuarios.gestionar')
    expect(
      destinoRedirect(() =>
        guard(args({ isAuthenticated: true, perfil: { rol: 'comercial' } }, ['extraccion.extraer'])),
      ),
    ).toBe('/')
  })
})

describe('cambio de contraseña forzado (S3)', () => {
  const pendiente = { rol: 'admin' as Rol, debe_cambiar_password: true }

  it('requireAuth manda a /cambiar-password mientras el flag está activo', () => {
    expect(destinoRedirect(() => requireAuth(args({ isAuthenticated: true, perfil: pendiente })))).toBe(
      '/cambiar-password',
    )
  })

  it('requireCapacidad manda a /cambiar-password aunque tenga la capacidad', () => {
    const guard = requireCapacidad('usuarios.gestionar')
    expect(
      destinoRedirect(() => guard(args({ isAuthenticated: true, perfil: pendiente }, ['usuarios.gestionar']))),
    ).toBe('/cambiar-password')
  })

  it('con el flag apagado no redirige', () => {
    const guard = requireCapacidad('usuarios.gestionar')
    expect(() =>
      guard(
        args({ isAuthenticated: true, perfil: { rol: 'admin', debe_cambiar_password: false } }, ['usuarios.gestionar']),
      ),
    ).not.toThrow()
  })

  it('requireSession (ruta de cambio) deja pasar con el flag activo: sin loop', () => {
    expect(() => requireSession(args({ isAuthenticated: true, perfil: pendiente }))).not.toThrow()
  })

  it('requireSession sigue mandando a /login sin sesión', () => {
    expect(destinoRedirect(() => requireSession(args({ isAuthenticated: false, perfil: null })))).toBe('/login')
  })
})
