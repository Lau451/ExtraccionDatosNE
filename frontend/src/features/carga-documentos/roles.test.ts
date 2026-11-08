import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { destinoRedirect, navegacionDeRol } from '@/test/capacidades'
import { Route as CargaRoute } from '@/routes/_authenticated.index'
import { Route as ValidarDetalleRoute } from '@/routes/_authenticated.validar-extraccion.$extractionId'
import { Route as ValidarListadoRoute } from '@/routes/_authenticated.validar-extraccion.index'

const ROLES_CON_EXTRACCION: Rol[] = ['admin', 'gerencia', 'lider_comercial', 'comercial']

describe('S1: carga de documentos (/)', () => {
  const guard = (rol: Rol | null) => () => CargaRoute.options.beforeLoad?.(navegacionDeRol(rol))

  it.each(ROLES_CON_EXTRACCION)('deja pasar a %s', (rol) => {
    expect(guard(rol)).not.toThrow()
  })

  it('redirige compras y superadmin a su home, nunca a / (sin loop)', () => {
    expect(destinoRedirect(guard('compras'))).toBe('/productos')
    expect(destinoRedirect(guard('superadmin'))).toBe('/superadmin/empresas')
  })

  it('sin perfil resuelto no redirige a / (evita el loop sobre la misma ruta)', () => {
    expect(destinoRedirect(guard(null))).not.toBe('/')
  })
})

describe('S2: validar extracción (/validar-extraccion/*)', () => {
  const guards = [ValidarListadoRoute.options.beforeLoad, ValidarDetalleRoute.options.beforeLoad]

  it.each(ROLES_CON_EXTRACCION)('deja pasar a %s', (rol) => {
    guards.forEach((g) => expect(() => g?.(navegacionDeRol(rol))).not.toThrow())
  })

  it.each<Rol>(['compras', 'superadmin'])('bloquea a %s', (rol) => {
    guards.forEach((g) => expect(() => g?.(navegacionDeRol(rol))).toThrow())
  })
})
