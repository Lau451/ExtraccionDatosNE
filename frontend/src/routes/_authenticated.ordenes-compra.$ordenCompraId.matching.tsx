import { createFileRoute } from '@tanstack/react-router'
import { OcMatchingDetalle } from '@/features/oc-matching/OcMatchingDetalle'

interface Search {
  // Presupuesto elegido en esta sesión (design.md D8): sobrevive a un reload
  // y es compartible por link. Opcional -- si falta, el servidor lo resuelve
  // (vínculos confirmados > query param > sugerido del ranking, D8) y
  // `OcMatchingDetalle` lo escribe acá al elegir.
  presupuesto?: string
}

export const Route = createFileRoute('/_authenticated/ordenes-compra/$ordenCompraId/matching')({
  validateSearch: (search: Record<string, unknown>): Search => ({
    presupuesto: typeof search.presupuesto === 'string' ? search.presupuesto : undefined,
  }),
  component: RouteComponent,
})

function RouteComponent() {
  const { ordenCompraId } = Route.useParams()
  const { presupuesto } = Route.useSearch()

  return <OcMatchingDetalle ordenCompraId={ordenCompraId} presupuestoId={presupuesto} />
}
