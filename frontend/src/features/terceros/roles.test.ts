import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { navegacionDeRol } from '@/test/capacidades'
import { Route as TerceroDetalleRoute } from '@/routes/_authenticated.terceros.$terceroId'
import { Route as TercerosRoute } from '@/routes/_authenticated.terceros'

describe('rutas de terceros (terceros.leer)', () => {
  const guards = [TercerosRoute.options.beforeLoad, TerceroDetalleRoute.options.beforeLoad]

  it.each<Rol>(['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])(
    'la lectura sigue abierta a %s',
    (rol) => {
      guards.forEach((g) => expect(() => g?.(navegacionDeRol(rol, '/terceros'))).not.toThrow())
    },
  )

  it('bloquea un rol sin capacidades (sistema)', () => {
    guards.forEach((g) => expect(() => g?.(navegacionDeRol('sistema', '/terceros'))).toThrow())
  })
})
