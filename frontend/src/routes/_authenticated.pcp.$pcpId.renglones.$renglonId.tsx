import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { RenglonDetalle } from '@/features/pcp/RenglonDetalle'

export const Route = createFileRoute('/_authenticated/pcp/$pcpId/renglones/$renglonId')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: () => {
    const { pcpId, renglonId } = Route.useParams()
    return <RenglonDetalle pcpId={pcpId} renglonId={renglonId} />
  },
})
