import type { Rol } from '@/features/auth/AuthContext'

/** Lectura de catálogo: productos, categorías, stock. Coincide con
 * `require_roles` de `services/productos` — ver prompt de la tarea. */
export const PRODUCTOS_READ_ROLES: Rol[] = [
  'superadmin',
  'admin',
  'gerencia',
  'lider_comercial',
  'comercial',
  'compras',
]

/** Escritura de catálogo: crear/editar/eliminar producto, cargar costo,
 * ajustar stock. */
export const PRODUCTOS_WRITE_ROLES: Rol[] = ['admin', 'gerencia', 'compras']

/** Escritura de categorías — subconjunto más chico que la escritura de
 * productos (no incluye `compras`). */
export const CATEGORIAS_WRITE_ROLES: Rol[] = ['admin', 'gerencia']

/** Lectura de costos — no incluye `lider_comercial` ni `comercial`, a
 * diferencia del resto del catálogo. */
export const COSTOS_READ_ROLES: Rol[] = ['superadmin', 'admin', 'gerencia', 'compras']

export function puedeRol(rol: Rol | undefined, permitidos: Rol[]): boolean {
  return !!rol && permitidos.includes(rol)
}
