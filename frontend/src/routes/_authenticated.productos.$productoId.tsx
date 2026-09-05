import { createFileRoute } from '@tanstack/react-router'
import { ProductoDetalle } from '@/features/productos/ProductoDetalle'
import { requireRole } from '@/features/auth/routeGuards'
import { PRODUCTOS_READ_ROLES } from '@/features/productos/roles'

export const Route = createFileRoute('/_authenticated/productos/$productoId')({
  beforeLoad: requireRole(...PRODUCTOS_READ_ROLES),
  component: RouteComponent,
})

function RouteComponent() {
  const { productoId } = Route.useParams()
  return <ProductoDetalle productoId={productoId} />
}
