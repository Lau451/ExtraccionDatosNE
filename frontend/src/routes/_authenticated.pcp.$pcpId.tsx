import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { PcpDetalle } from '@/features/pcp/PcpDetalle'
import { PCP_READ_ROLES } from '@/features/pcp/roles'

export const Route = createFileRoute('/_authenticated/pcp/$pcpId')({
  beforeLoad: requireRole(...PCP_READ_ROLES),
  component: () => <PcpDetalle pcpId={Route.useParams().pcpId} />,
})
