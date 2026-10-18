import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { OcResumen } from '@/features/oc-resumen/OcResumen'
import { OC_RESUMEN_READ_ROLES } from '@/features/oc-resumen/roles'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/')({
  beforeLoad: requireRole(...OC_RESUMEN_READ_ROLES),
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <OcResumen ordenCompraId={ordenCompraId} />
}
