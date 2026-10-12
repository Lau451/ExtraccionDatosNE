import { createFileRoute } from '@tanstack/react-router'
import { OcResumen } from '@/features/oc-resumen/OcResumen'

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/')({
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()

  return <OcResumen ordenCompraId={ordenCompraId} />
}
