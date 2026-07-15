import { redirect } from '@tanstack/react-router'
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

export function requireRole(...roles: Rol[]) {
  return (args: GuardArgs) => {
    requireAuth(args)
    if (!args.context.auth.perfil || !roles.includes(args.context.auth.perfil.rol)) {
      throw redirect({ to: '/' })
    }
  }
}
