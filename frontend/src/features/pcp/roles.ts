import type { Rol } from '@/features/auth/AuthContext'

export const PCP_READ_ROLES: Rol[] = ['superadmin', 'admin', 'gerencia', 'compras']
export const PCP_WRITE_ROLES: Rol[] = ['admin', 'gerencia', 'compras']

export function puedeRol(rol: Rol | undefined, permitidos: Rol[]): boolean {
  return !!rol && permitidos.includes(rol)
}
