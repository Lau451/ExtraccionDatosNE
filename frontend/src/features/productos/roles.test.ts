import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { navegacionDeRol } from '@/test/capacidades'
import { Route as ProductoDetalleRoute } from '@/routes/_authenticated.productos.$productoId'
import { Route as ProductosRoute } from '@/routes/_authenticated.productos'

describe('rutas de productos (productos.leer)', () => {
  const guards = [ProductosRoute.options.beforeLoad, ProductoDetalleRoute.options.beforeLoad]

  it.each<Rol>(['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])(
    'deja pasar a %s',
    (rol) => {
      guards.forEach((g) => expect(() => g?.(navegacionDeRol(rol, '/productos'))).not.toThrow())
    },
  )

  it('bloquea un rol sin capacidades (sistema)', () => {
    guards.forEach((g) => expect(() => g?.(navegacionDeRol('sistema', '/productos'))).toThrow())
  })
})
