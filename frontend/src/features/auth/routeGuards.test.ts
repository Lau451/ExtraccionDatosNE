import { describe, expect, it } from 'vitest'
import { requireAuth, requireRole } from './routeGuards'

function args(auth: { isAuthenticated: boolean; perfil: { rol: 'admin' | 'superadmin' | 'comercial' } | null }) {
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
  it('redirige a / si el perfil todavía no resolvió (caso D-LOGIN-005/007)', () => {
    const guard = requireRole('admin', 'superadmin')
    expect(() => guard(args({ isAuthenticated: true, perfil: null }))).toThrow()
  })

  it('redirige a / si el rol del perfil no está permitido', () => {
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
