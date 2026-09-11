import { describe, expect, it } from 'vitest'
import { Route as PcpDetailRoute } from '@/routes/_authenticated.pcp.$pcpId'
import { Route as PcpIndexRoute } from '@/routes/_authenticated.pcp.index'
import { Route as PcpRoute } from '@/routes/_authenticated.pcp'
import { muestraNavegacionPcp } from '@/features/shell/Sidebar'
import { PCP_READ_ROLES, PCP_WRITE_ROLES, puedeRol } from './roles'

function navigationArgs(rol: 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras') {
  return {
    context: { auth: { isAuthenticated: true, perfil: { rol } } },
    location: { href: '/pcp/pcp-123' },
  }
}

describe('roles PCP', () => {
  it('habilita lectura para los cuatro roles definidos por el backend', () => {
    expect(PCP_READ_ROLES).toEqual(['superadmin', 'admin', 'gerencia', 'compras'])
    expect(PCP_READ_ROLES.every((rol) => puedeRol(rol, PCP_READ_ROLES))).toBe(true)
  })

  it('habilita escritura para cada uno de los tres roles de escritura', () => {
    expect(PCP_WRITE_ROLES).toEqual(['admin', 'gerencia', 'compras'])
    expect(puedeRol('admin', PCP_WRITE_ROLES)).toBe(true)
    expect(puedeRol('gerencia', PCP_WRITE_ROLES)).toBe(true)
    expect(puedeRol('compras', PCP_WRITE_ROLES)).toBe(true)
  })

  it('niega escritura al superadmin, aunque pueda leer PCP', () => {
    expect(puedeRol('superadmin', PCP_WRITE_ROLES)).toBe(false)
  })

  it('niega los roles comerciales que no pueden navegar directamente a PCP', () => {
    expect(puedeRol('lider_comercial', PCP_READ_ROLES)).toBe(false)
    expect(puedeRol('comercial', PCP_READ_ROLES)).toBe(false)
  })

  const routeGuards = [
    PcpRoute.options.beforeLoad,
    PcpIndexRoute.options.beforeLoad,
    PcpDetailRoute.options.beforeLoad,
  ]

  it('oculta la navegación PCP y bloquea la navegación directa para roles ajenos', () => {
    expect(muestraNavegacionPcp('superadmin')).toBe(true)
    expect(muestraNavegacionPcp('compras')).toBe(true)
    expect(muestraNavegacionPcp('lider_comercial')).toBe(false)
    expect(muestraNavegacionPcp('comercial')).toBe(false)
    expect(routeGuards).toHaveLength(3)
    routeGuards.forEach((routeGuard) => {
      expect(() => routeGuard?.(navigationArgs('comercial') as never)).toThrow()
    })
  })

  it('permite navegar directamente a las rutas PCP anidadas con un rol de lectura', () => {
    routeGuards.forEach((routeGuard) => {
      expect(() => routeGuard?.(navigationArgs('compras') as never)).not.toThrow()
    })
  })
})
