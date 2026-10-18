import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { PlanificacionEntregas } from '@/features/oc-entregas/PlanificacionEntregas'
import { OC_RESUMEN_ACCIONES_ROLES } from '@/features/oc-resumen/roles'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/entregas')({
  beforeLoad: requireRole(...OC_RESUMEN_ACCIONES_ROLES),
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <PlanificacionEntregas ordenCompraId={ordenCompraId} />
}
