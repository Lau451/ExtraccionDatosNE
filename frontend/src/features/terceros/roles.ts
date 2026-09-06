import type { Rol } from '@/features/auth/AuthContext'

/** Lectura de terceros/direcciones/contactos — los 6 roles de negocio, a
 * diferencia de productos donde costos tiene un subconjunto más chico. Ver
 * prompt de la tarea. */
export const TERCEROS_READ_ROLES: Rol[] = [
  'superadmin',
  'admin',
  'gerencia',
  'lider_comercial',
  'comercial',
  'compras',
]

/** Escritura de terceros/direcciones/contactos — a diferencia de productos
 * (donde el patrón es "todos menos superadmin" ya sería coincidente acá),
 * pero se lista explícito porque así lo define el prompt de la tarea. */
export const TERCEROS_WRITE_ROLES: Rol[] = [
  'admin',
  'gerencia',
  'lider_comercial',
  'comercial',
  'compras',
]

/** Lectura de catálogos de apoyo (sectores de contacto, condiciones y
 * formas de pago) — mismos 6 roles que la lectura de terceros. */
export const CATALOGOS_COMERCIALES_READ_ROLES: Rol[] = TERCEROS_READ_ROLES

/** Escritura de catálogos de apoyo — subconjunto más chico, igual criterio
 * que `CATEGORIAS_WRITE_ROLES` en productos. */
export const CATALOGOS_COMERCIALES_WRITE_ROLES: Rol[] = ['admin', 'gerencia']

export function puedeRol(rol: Rol | undefined, permitidos: Rol[]): boolean {
  return !!rol && permitidos.includes(rol)
}
