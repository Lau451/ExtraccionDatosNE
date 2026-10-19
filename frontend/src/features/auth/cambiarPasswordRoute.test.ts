import { describe, expect, it } from 'vitest'
import { Route as AuthenticatedRoute } from '@/routes/_authenticated'
import { Route as CambiarPasswordRoute } from '@/routes/cambiar-password'

function navigationArgs(isAuthenticated: boolean, debeCambiar: boolean) {
  return {
    context: {
      auth: { isAuthenticated, perfil: isAuthenticated ? { rol: 'admin', debe_cambiar_password: debeCambiar } : null },
    },
    location: { href: '/mi-cuenta' },
  }
}

function destino(fn: () => unknown): string | undefined {
  try {
    fn()
  } catch (error) {
    return (error as { options: { to: string } }).options.to
  }
  return undefined
}

describe('S3: guard global del cambio forzado', () => {
  it('el layout protegido manda a /cambiar-password mientras el flag está activo', () => {
    expect(destino(() => AuthenticatedRoute.options.beforeLoad?.(navigationArgs(true, true) as never))).toBe(
      '/cambiar-password',
    )
  })

  it('el layout protegido deja pasar con el flag apagado', () => {
    expect(destino(() => AuthenticatedRoute.options.beforeLoad?.(navigationArgs(true, false) as never))).toBeUndefined()
  })

  it('/cambiar-password no se redirige a sí misma con el flag activo', () => {
    expect(destino(() => CambiarPasswordRoute.options.beforeLoad?.(navigationArgs(true, true) as never))).toBeUndefined()
  })

  it('/cambiar-password exige sesión', () => {
    expect(destino(() => CambiarPasswordRoute.options.beforeLoad?.(navigationArgs(false, false) as never))).toBe('/login')
  })
})
