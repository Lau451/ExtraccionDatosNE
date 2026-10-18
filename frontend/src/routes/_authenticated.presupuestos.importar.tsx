import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ImportarPresupuestosLegacy } from '@/features/presupuestos-import/ImportarPresupuestosLegacy'
import { PRESUPUESTOS_LEGACY_IMPORT_ROLES } from '@/features/presupuestos-import/roles'

/** Mismos roles que `/pcp/imports/presupuestos-legacy` (spec S6: solo
 * `admin`); ya no coincide con `PCP_WRITE_ROLES`. */
export const Route = createFileRoute('/_authenticated/presupuestos/importar')({
  beforeLoad: requireRole(...PRESUPUESTOS_LEGACY_IMPORT_ROLES),
  component: ImportarPresupuestosLegacy,
})
