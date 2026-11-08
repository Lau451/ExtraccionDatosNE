import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { navegacionDeRol } from '@/test/capacidades'
import { Route as UsuariosRoute } from '@/routes/_authenticated.admin.usuarios'

describe('S7: guard de /admin/usuarios', () => {
  it.each<Rol>(['admin', 'superadmin', 'gerencia'])('deja pasar a %s', (rol) => {
    expect(() => UsuariosRoute.options.beforeLoad?.(navegacionDeRol(rol, '/admin/usuarios'))).not.toThrow()
  })

  it.each<Rol>(['lider_comercial', 'comercial', 'compras'])('sigue bloqueando a %s', (rol) => {
    expect(() => UsuariosRoute.options.beforeLoad?.(navegacionDeRol(rol, '/admin/usuarios'))).toThrow()
  })
})
