import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ConsultaDetalle } from '@/features/pcp/ConsultaDetalle'

export const Route = createFileRoute('/_authenticated/pcp/consultas/$consultaId')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: () => <ConsultaDetalle consultaId={Route.useParams().consultaId} />,
})
