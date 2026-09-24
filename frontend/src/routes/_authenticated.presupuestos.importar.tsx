import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ImportarPresupuestosLegacy } from '@/features/presupuestos-import/ImportarPresupuestosLegacy'
import { PCP_WRITE_ROLES } from '@/features/pcp/roles'

/** Gateado con `PCP_WRITE_ROLES` (mismos roles que
 * `ROLES_ESCRITURA_PCP`/`/pcp/imports/presupuestos-legacy`), no con un
 * roles.ts propio -- feature doc `presupuestos-legacy-import-ui.md`
 * Decisions: "same roles as the endpoint". */
export const Route = createFileRoute('/_authenticated/presupuestos/importar')({
  beforeLoad: requireRole(...PCP_WRITE_ROLES),
  component: ImportarPresupuestosLegacy,
})
