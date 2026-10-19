import { redirect } from '@tanstack/react-router'
import { CARGA_DOCUMENTOS_ROLES } from '@/features/carga-documentos/roles'
import type { Rol } from './AuthContext'

interface GuardArgs {
  context: { auth: { isAuthenticated: boolean; perfil: { rol: Rol; debe_cambiar_password?: boolean } | null } }
  location: { href: string }
}

// Solo exige sesión. La usa directamente /cambiar-password: si usara
// requireAuth, el chequeo del cambio forzado la redirigiría a sí misma (loop).
export function requireSession({ context, location }: GuardArgs) {
  if (!context.auth.isAuthenticated) {
    throw redirect({ to: '/login', search: { redirect: location.href } })
  }
}

// Toda ruta protegida pasa por acá (el layout _authenticated y requireRole):
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
// /mi-cuenta, que no tiene guard de rol, por la misma razón.
export function homeForRol(rol: Rol | undefined): string {
  if (rol && CARGA_DOCUMENTOS_ROLES.includes(rol)) return '/'
  if (rol === 'compras') return '/productos'
  if (rol === 'superadmin') return '/superadmin/empresas'
  return '/mi-cuenta'
}

export function requireRole(...roles: Rol[]) {
  return (args: GuardArgs) => {
    requireAuth(args)
    const rol = args.context.auth.perfil?.rol
    if (!rol || !roles.includes(rol)) {
      throw redirect({ to: homeForRol(rol) })
    }
  }
}
