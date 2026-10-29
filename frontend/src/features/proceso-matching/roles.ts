import type { Rol } from '@/features/auth/AuthContext'

/** Same roles the backend accepts on the matching endpoints
 * (`services/presupuestacion/matching/router.py::_ROLES_MATCHING`). */
export const MATCHING_ROLES: Rol[] = ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial']
