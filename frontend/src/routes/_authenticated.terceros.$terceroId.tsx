import { createFileRoute } from '@tanstack/react-router'
import { TerceroDetalle } from '@/features/terceros/TerceroDetalle'
import { requireCapacidad } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/terceros/$terceroId')({
  beforeLoad: requireCapacidad('terceros.leer'),
  component: RouteComponent,
})

function RouteComponent() {
  const { terceroId } = Route.useParams()
  return <TerceroDetalle terceroId={terceroId} />
}
