import type { Rol } from '@/features/auth/AuthContext'

/** Importación de presupuestos legacy (spec S6): solo `admin`, espejo de
 * `/pcp/imports/presupuestos-legacy`. Más chico que `PCP_WRITE_ROLES`, que
 * sigue gateando la importación de PCP. */
export const PRESUPUESTOS_LEGACY_IMPORT_ROLES: Rol[] = ['admin']
