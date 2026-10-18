import type { Rol } from '@/features/auth/AuthContext'

/** Pantalla de usuarios (spec S7). `gerencia` gestiona solo roles inferiores
 * de su droguería — ver `ROLES_BASE` y `rolesProtegidos` en GestionUsuarios. */
export const USUARIOS_ROLES: Rol[] = ['admin', 'superadmin', 'gerencia']
