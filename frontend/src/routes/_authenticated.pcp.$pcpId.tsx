import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { PcpDetalle } from '@/features/pcp/PcpDetalle'

export const Route = createFileRoute('/_authenticated/pcp/$pcpId')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: () => <PcpDetalle pcpId={Route.useParams().pcpId} />,
})
