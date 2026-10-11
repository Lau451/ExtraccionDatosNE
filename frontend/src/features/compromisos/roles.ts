import type { Rol } from '@/features/auth/AuthContext'

// Espejo de `_ROLES_LECTURA` en compromisos/router.py, sin superadmin: no tiene
// droguería y el endpoint le responde 422.
export const COMPROMISOS_READ_ROLES: Rol[] = ['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras']
