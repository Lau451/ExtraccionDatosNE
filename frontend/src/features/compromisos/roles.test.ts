import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { navegacionDeRol } from '@/test/capacidades'
import { Route as CompromisosRoute } from '@/routes/_authenticated.compromisos'

describe('S9: guard de /compromisos', () => {
  it('bloquea la navegación directa de superadmin', () => {
    expect(() => CompromisosRoute.options.beforeLoad?.(navegacionDeRol('superadmin', '/compromisos'))).toThrow()
  })

  it.each<Rol>(['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])('deja pasar a %s', (rol) => {
    expect(() => CompromisosRoute.options.beforeLoad?.(navegacionDeRol(rol, '/compromisos'))).not.toThrow()
  })
})
