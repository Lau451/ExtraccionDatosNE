import { redirect } from '@tanstack/react-router'
import { CARGA_DOCUMENTOS_ROLES } from '@/features/carga-documentos/roles'
import type { Rol } from './AuthContext'

interface GuardArgs {
  context: { auth: { isAuthenticated: boolean; perfil: { rol: Rol } | null } }
  location: { href: string }
}

export function requireAuth({ context, location }: GuardArgs) {
  if (!context.auth.isAuthenticated) {
    throw redirect({ to: '/login', search: { redirect: location.href } })
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
