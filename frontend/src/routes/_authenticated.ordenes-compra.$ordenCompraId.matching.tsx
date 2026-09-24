import { createFileRoute } from '@tanstack/react-router'

interface Search {
  // Presupuesto elegido en esta sesión (design.md D8): sobrevive a un reload
  // y es compartible por link. Opcional -- si falta, el servidor lo resuelve
  // (vínculos confirmados > query param > sugerido del ranking, D8) y
  // `OcMatchingDetalle` (Phase 7, tasks.md) lo escribe acá al elegir.
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

  // Placeholder: `OcMatchingDetalle` (frontend/src/features/oc-matching/, Phase 7
  // de tasks.md) todavía no existe -- esta ruta se crea ahora (Phase 5) para que
  // `useNavigate` de Phase 6 tipe correctamente contra `routeTree.gen.ts`. El
  // container real reemplaza este cuerpo sin tocar `Route.useParams()` /
  // `Route.useSearch()`, que ya quedan resueltos con la forma final (D8).
  return (
    <div className="mx-auto max-w-2xl space-y-4 px-6 py-10">
      <h1 className="text-xl font-semibold text-slate-900">Matching de orden de compra</h1>
      <p className="text-sm text-slate-600">
        Orden de compra {ordenCompraId}
        {presupuesto ? ` -- presupuesto ${presupuesto}` : ''}. Pantalla en construcción.
      </p>
    </div>
  )
}
