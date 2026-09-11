import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { RenglonDetalle } from '@/features/pcp/RenglonDetalle'
import { PCP_READ_ROLES } from '@/features/pcp/roles'

export const Route = createFileRoute('/_authenticated/pcp/$pcpId/renglones/$renglonId')({
  beforeLoad: requireRole(...PCP_READ_ROLES),
  component: () => {
    const { pcpId, renglonId } = Route.useParams()
    return <RenglonDetalle pcpId={pcpId} renglonId={renglonId} />
  },
})
