import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { listarProcesosConMatchingPendiente } from '@/lib/api/matching'
import { CLASE_LEGIBLE, contar } from './textos'

/** Procesos with renglones still pendiente or sugerido (presupuestador-v1 T3c,
 * S10 "listado de pendientes"), closest vencimiento first. Each one opens its
 * matching screen. */
export function ProcesosMatchingListado() {
  const query = useQuery({
    queryKey: ['procesos-matching-pendiente'],
    queryFn: listarProcesosConMatchingPendiente,
  })

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-900">Matching de catálogo</h1>
        <p className="text-sm text-slate-600">Procesos con renglones que todavía no tienen producto confirmado.</p>
      </header>

      {query.isPending ? (
        <p className="text-sm text-slate-500">Cargando procesos…</p>
      ) : query.isError ? (
        <p className="text-sm text-red-600">
          {query.error instanceof Error ? query.error.message : 'No se pudieron cargar los procesos.'}
        </p>
      ) : query.data.length === 0 ? (
        <p className="text-sm text-slate-500">No hay procesos con renglones sin resolver.</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-md border border-slate-200 bg-white">
          {query.data.map((proceso) => (
            <li key={proceso.proceso_comercial_id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0 space-y-0.5">
                <Link
                  to="/procesos-comerciales/$procesoId/matching"
                  params={{ procesoId: proceso.proceso_comercial_id }}
                  className="block truncate text-sm font-medium text-slate-900 hover:underline"
                >
                  {proceso.proceso}
                </Link>
                <p className="text-sm text-slate-500">
                  {[proceso.cliente, CLASE_LEGIBLE[proceso.clase] ?? proceso.clase].filter(Boolean).join(' · ')}
                </p>
              </div>
              <p className="shrink-0 text-sm tabular-nums text-slate-600">
                {[contar(proceso.pendientes, 'pendiente', 'pendientes'), contar(proceso.sugeridos, 'sugerido', 'sugeridos')].join(
                  ' · ',
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
