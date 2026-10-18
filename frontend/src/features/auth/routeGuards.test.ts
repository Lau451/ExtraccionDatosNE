import { describe, expect, it } from 'vitest'
import type { Rol } from './AuthContext'
import { homeForRol, requireAuth, requireRole } from './routeGuards'

function args(auth: { isAuthenticated: boolean; perfil: { rol: Rol } | null }) {
  return { context: { auth }, location: { href: '/admin/usuarios' } }
}

describe('requireAuth', () => {
  it('redirige a /login si no hay sesión', () => {
    expect(() => requireAuth(args({ isAuthenticated: false, perfil: null }))).toThrow()
  })

  it('no hace nada si hay sesión', () => {
    expect(() => requireAuth(args({ isAuthenticated: true, perfil: null }))).not.toThrow()
  })
})

describe('requireRole', () => {
  it('redirige si el perfil todavía no resolvió (caso D-LOGIN-005/007)', () => {
    const guard = requireRole('admin', 'superadmin')
    expect(() => guard(args({ isAuthenticated: true, perfil: null }))).toThrow()
  })

  it('redirige si el rol del perfil no está permitido', () => {
    const guard = requireRole('admin', 'superadmin')
    expect(() =>
      guard(args({ isAuthenticated: true, perfil: { rol: 'comercial' } })),
    ).toThrow()
  })

  it('deja pasar si el rol del perfil está permitido', () => {
    const guard = requireRole('admin', 'superadmin')
    expect(() =>
      guard(args({ isAuthenticated: true, perfil: { rol: 'admin' } })),
    ).not.toThrow()
  })

  it('redirige a /login antes de evaluar el rol si no hay sesión', () => {
    const guard = requireRole('admin')
    expect(() => guard(args({ isAuthenticated: false, perfil: null }))).toThrow()
  })
})

function destinoRedirect(fn: () => void): string | undefined {
  try {
    fn()
  } catch (error) {
    return (error as { options: { to: string } }).options.to
  }
  return undefined
}

describe('homeForRol (S9: aterrizaje sin loop)', () => {
  it.each(['admin', 'gerencia', 'lider_comercial', 'comercial'] as const)('%s aterriza en / (carga)', (rol) => {
    expect(homeForRol(rol)).toBe('/')
  })

  it('compras aterriza en /productos y superadmin en /superadmin/empresas', () => {
    expect(homeForRol('compras')).toBe('/productos')
    expect(homeForRol('superadmin')).toBe('/superadmin/empresas')
  })

  it('un rol denegado es redirigido a su home, no a /', () => {
    const guard = requireRole('admin')
    expect(destinoRedirect(() => guard(args({ isAuthenticated: true, perfil: { rol: 'compras' } })))).toBe('/productos')
  })

  it('sigue redirigiendo a / a un rol de carga denegado (comportamiento previo)', () => {
    const guard = requireRole('admin', 'superadmin')
    expect(destinoRedirect(() => guard(args({ isAuthenticated: true, perfil: { rol: 'comercial' } })))).toBe('/')
  })
})
