import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ImportLegacyPcp } from '@/features/pcp/ImportLegacyPcp'
import { PCP_WRITE_ROLES } from '@/features/pcp/roles'

/** Único ruteo PCP que usa `PCP_WRITE_ROLES` en vez de `PCP_READ_ROLES`
 * (spec `pcp-ui-legacy-import`, "Read-only role cannot access the import
 * screen"): `superadmin` puede leer todo PCP pero no puede importar. */
export const Route = createFileRoute('/_authenticated/pcp/imports')({
  beforeLoad: requireRole(...PCP_WRITE_ROLES),
  component: ImportLegacyPcp,
})
