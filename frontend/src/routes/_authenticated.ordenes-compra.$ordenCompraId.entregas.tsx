import { createFileRoute } from '@tanstack/react-router'
import { PlanificacionEntregas } from '@/features/oc-entregas/PlanificacionEntregas'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/entregas')({
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <PlanificacionEntregas ordenCompraId={ordenCompraId} />
}
