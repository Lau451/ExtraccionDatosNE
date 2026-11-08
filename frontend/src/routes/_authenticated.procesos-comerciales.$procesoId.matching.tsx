import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ProcesoMatchingDetalle } from '@/features/proceso-matching/ProcesoMatchingDetalle'

export const Route = createFileRoute('/_authenticated/procesos-comerciales/$procesoId/matching')({
  beforeLoad: requireCapacidad('matching.usar'),
  component: RouteComponent,
})

function RouteComponent() {
  const { procesoId } = Route.useParams()

  return <ProcesoMatchingDetalle procesoId={procesoId} />
}
