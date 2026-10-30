import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ProcesoMatchingDetalle } from '@/features/proceso-matching/ProcesoMatchingDetalle'
import { MATCHING_ROLES } from '@/features/proceso-matching/roles'

export const Route = createFileRoute('/_authenticated/procesos-comerciales/$procesoId/matching')({
  beforeLoad: requireRole(...MATCHING_ROLES),
  component: RouteComponent,
})

function RouteComponent() {
  const { procesoId } = Route.useParams()

  return <ProcesoMatchingDetalle procesoId={procesoId} />
}
