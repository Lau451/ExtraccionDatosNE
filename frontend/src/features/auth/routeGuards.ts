import { redirect } from '@tanstack/react-router'
import type { Rol } from './AuthContext'
import type { Capacidad } from './capacidades'

interface GuardArgs {
  context: {
    auth: {
      isAuthenticated: boolean
      perfil: { rol: Rol; debe_cambiar_password?: boolean } | null
      capacidades: readonly Capacidad[]
    }
  }
  location: { href: string }
}

// Solo exige sesión. La usa directamente /cambiar-password: si usara
// requireAuth, el chequeo del cambio forzado la redirigiría a sí misma (loop).
export function requireSession({ context, location }: GuardArgs) {
  if (!context.auth.isAuthenticated) {
    throw redirect({ to: '/login', search: { redirect: location.href } })
  }
}

// Toda ruta protegida pasa por acá (el layout _authenticated y requireCapacidad):
// mientras la contraseña sea temporal se manda a cambiarla (spec S3).
export function requireAuth(args: GuardArgs) {
  requireSession(args)
  if (args.context.auth.perfil?.debe_cambiar_password) {
    throw redirect({ to: '/cambiar-password' })
  }
}

// Pantalla de aterrizaje de cada rol (spec S9). "/" (carga de documentos)
// ya no es de todos: si un rol denegado rebotara siempre a "/", el guard de
// "/" lo volvería a rebotar ahí mismo (loop). Sin perfil resuelto se va a
// /mi-cuenta, que no tiene guard, por la misma razón.
export function homeForRol(rol: Rol | undefined, capacidades: readonly Capacidad[]): string {
  if (rol && capacidades.includes('extraccion.extraer')) return '/'
  if (rol === 'compras') return '/productos'
  if (rol === 'superadmin') return '/superadmin/empresas'
  return '/mi-cuenta'
}

export function requireCapacidad(capacidad: Capacidad) {
  return (args: GuardArgs) => {
    requireAuth(args)
    const { perfil, capacidades } = args.context.auth
    if (!perfil || !capacidades.includes(capacidad)) {
      throw redirect({ to: homeForRol(perfil?.rol, capacidades) })
    }
  }
}
