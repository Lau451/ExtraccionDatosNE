import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { navegacionDeRol } from '@/test/capacidades'
import { Route as PcpDetailRoute } from '@/routes/_authenticated.pcp.$pcpId'
import { Route as PcpRenglonRoute } from '@/routes/_authenticated.pcp.$pcpId.renglones.$renglonId'
import { Route as PcpCatalogoRoute } from '@/routes/_authenticated.pcp.catalogo'
import { Route as PcpConsultaRoute } from '@/routes/_authenticated.pcp.consultas.$consultaId'
import { Route as PcpIndexRoute } from '@/routes/_authenticated.pcp.index'
import { Route as PcpRoute } from '@/routes/_authenticated.pcp'

const navegacion = (rol: Rol) => navegacionDeRol(rol, '/pcp/pcp-123')

describe('rutas PCP (pcp.leer)', () => {
  const routeGuards = [
    PcpRoute.options.beforeLoad,
    PcpIndexRoute.options.beforeLoad,
    PcpDetailRoute.options.beforeLoad,
    PcpRenglonRoute.options.beforeLoad,
    PcpCatalogoRoute.options.beforeLoad,
    PcpConsultaRoute.options.beforeLoad,
  ]

  it.each<Rol>(['superadmin', 'admin', 'gerencia', 'compras'])('deja navegar directamente a %s', (rol) => {
    expect(routeGuards.every((g) => typeof g === 'function')).toBe(true)
    routeGuards.forEach((routeGuard) => {
      expect(() => routeGuard?.(navegacion(rol))).not.toThrow()
    })
  })

  it.each<Rol>(['lider_comercial', 'comercial'])('bloquea la navegación directa de %s', (rol) => {
    routeGuards.forEach((routeGuard) => {
      expect(() => routeGuard?.(navegacion(rol))).toThrow()
    })
  })
})
