import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { OcResumen } from '@/features/oc-resumen/OcResumen'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/')({
  beforeLoad: requireCapacidad('oc_resumen.leer'),
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <OcResumen ordenCompraId={ordenCompraId} />
}
