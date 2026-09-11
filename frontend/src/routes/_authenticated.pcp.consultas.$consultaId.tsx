import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ConsultaDetalle } from '@/features/pcp/ConsultaDetalle'
import { PCP_READ_ROLES } from '@/features/pcp/roles'

export const Route = createFileRoute('/_authenticated/pcp/consultas/$consultaId')({
  beforeLoad: requireRole(...PCP_READ_ROLES),
  component: () => <ConsultaDetalle consultaId={Route.useParams().consultaId} />,
})
