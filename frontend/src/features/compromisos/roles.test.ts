import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { Route as CompromisosRoute } from '@/routes/_authenticated.compromisos'

function navigationArgs(rol: Rol) {
  return {
    context: { auth: { isAuthenticated: true, perfil: { rol } } },
    location: { href: '/compromisos' },
  }
}

describe('S9: guard de /compromisos', () => {
  it('bloquea la navegación directa de superadmin', () => {
    expect(() => CompromisosRoute.options.beforeLoad?.(navigationArgs('superadmin') as never)).toThrow()
  })

  it.each<Rol>(['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])('deja pasar a %s', (rol) => {
    expect(() => CompromisosRoute.options.beforeLoad?.(navigationArgs(rol) as never)).not.toThrow()
  })
})
