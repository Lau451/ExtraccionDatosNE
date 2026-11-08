import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ImportLegacyPcp } from '@/features/pcp/ImportLegacyPcp'

/** Único ruteo PCP que usa `pcp.escribir` en vez de `pcp.leer`
 * (spec `pcp-ui-legacy-import`, "Read-only role cannot access the import
 * screen"): `superadmin` puede leer todo PCP pero no puede importar. */
export const Route = createFileRoute('/_authenticated/pcp/imports')({
  beforeLoad: requireCapacidad('pcp.escribir'),
  component: ImportLegacyPcp,
})
