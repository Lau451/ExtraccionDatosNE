import { createFileRoute } from '@tanstack/react-router'
import { ValidarExtraccionDetalle } from '@/features/validar-extraccion/ValidarExtraccionDetalle'

interface Search {
  rowCount: number
}

export const Route = createFileRoute('/_authenticated/validar-extraccion/$extractionId')({
  // rowCount llega como search param desde el Link de PendientesTable -- ver
  // features/validar-extraccion/ValidarExtraccionDetalle.tsx (gate D7).
  validateSearch: (search: Record<string, unknown>): Search => ({
    rowCount: Number(search.rowCount) || 0,
  }),
  component: RouteComponent,
})

function RouteComponent() {
  const { extractionId } = Route.useParams()
  const { rowCount } = Route.useSearch()
  return <ValidarExtraccionDetalle extractionId={extractionId} rowCountHint={rowCount} />
}
