import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import { Route as EntregasRoute } from '@/routes/_authenticated.ordenes-compra.$ordenCompraId.entregas'
import { Route as ResumenRoute } from '@/routes/_authenticated.ordenes-compra.$ordenCompraId.index'
import { Route as MatchingRoute } from '@/routes/_authenticated.ordenes-compra.$ordenCompraId.matching'

function navigationArgs(rol: Rol) {
  return {
    context: { auth: { isAuthenticated: true, perfil: { rol } } },
    location: { href: '/ordenes-compra/oc-1' },
  }
}

describe('S8/S9: rutas de órdenes de compra', () => {
  const guardsAcciones = [MatchingRoute.options.beforeLoad, EntregasRoute.options.beforeLoad]

  it.each<Rol>(['admin', 'gerencia', 'lider_comercial', 'comercial'])('matching y entregas dejan pasar a %s', (rol) => {
    guardsAcciones.forEach((g) => expect(() => g?.(navigationArgs(rol) as never)).not.toThrow())
  })

  it.each<Rol>(['compras', 'superadmin'])('matching y entregas bloquean a %s', (rol) => {
    expect(guardsAcciones.every((g) => typeof g === 'function')).toBe(true)
    guardsAcciones.forEach((g) => expect(() => g?.(navigationArgs(rol) as never)).toThrow())
  })

  it.each<Rol>(['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])(
    'el resumen tiene guard y deja pasar a %s',
    (rol) => {
      expect(typeof ResumenRoute.options.beforeLoad).toBe('function')
      expect(() => ResumenRoute.options.beforeLoad?.(navigationArgs(rol) as never)).not.toThrow()
    },
  )
})
