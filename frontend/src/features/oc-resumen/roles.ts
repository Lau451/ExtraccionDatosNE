import type { Rol } from '@/features/auth/AuthContext'

// Roles que pueden abrir matching y planificación de entregas desde el resumen
// (mismos que las pantallas destino); `compras` solo lee el resumen.
export const OC_RESUMEN_ACCIONES_ROLES: Rol[] = ['admin', 'gerencia', 'lider_comercial', 'comercial']

/** Lectura del resumen de la OC: los 6 roles de negocio (spec S9). */
export const OC_RESUMEN_READ_ROLES: Rol[] = [
  'superadmin',
  'admin',
  'gerencia',
  'lider_comercial',
  'comercial',
  'compras',
]

export function puedeRol(rol: Rol | undefined, permitidos: Rol[]): boolean {
  return !!rol && permitidos.includes(rol)
}
