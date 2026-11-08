import { createFileRoute } from '@tanstack/react-router'
import { ProductoDetalle } from '@/features/productos/ProductoDetalle'
import { requireCapacidad } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/productos/$productoId')({
  beforeLoad: requireCapacidad('productos.leer'),
  component: RouteComponent,
})

function RouteComponent() {
  const { productoId } = Route.useParams()
  return <ProductoDetalle productoId={productoId} />
}
