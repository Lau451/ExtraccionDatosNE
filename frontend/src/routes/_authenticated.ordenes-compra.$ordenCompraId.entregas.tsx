import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { PlanificacionEntregas } from '@/features/oc-entregas/PlanificacionEntregas'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/entregas')({
  beforeLoad: requireCapacidad('oc_resumen.acciones'),
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <PlanificacionEntregas ordenCompraId={ordenCompraId} />
}
