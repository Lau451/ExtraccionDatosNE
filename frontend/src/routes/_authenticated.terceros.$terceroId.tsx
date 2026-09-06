import { createFileRoute } from '@tanstack/react-router'
import { TerceroDetalle } from '@/features/terceros/TerceroDetalle'
import { requireRole } from '@/features/auth/routeGuards'
import { TERCEROS_READ_ROLES } from '@/features/terceros/roles'

export const Route = createFileRoute('/_authenticated/terceros/$terceroId')({
  beforeLoad: requireRole(...TERCEROS_READ_ROLES),
  component: RouteComponent,
})

function RouteComponent() {
  const { terceroId } = Route.useParams()
  return <TerceroDetalle terceroId={terceroId} />
}
