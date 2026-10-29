import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { confirmarMatching, marcarSinMatch, obtenerMatchingProceso } from '@/lib/api/matching'
import { RenglonMatchingFila } from './components/RenglonMatchingFila'

const CLASE_LEGIBLE: Record<string, string> = {
  licitacion: 'Licitación',
  cotizacion: 'Directa',
}

function contar(cantidad: number, singular: string, plural: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : plural}`
}

interface Props {
  procesoId: string
}

/** Matching screen of one proceso comercial (presupuestador-v1 T3, S4/S10):
 * every renglón with its estado, chosen producto and candidatos. Each decision
 * (confirm a candidato or a catalog producto, sin match) reloads the proceso,
 * since the backend responds with the single renglón, not the whole screen. */
export function ProcesoMatchingDetalle({ procesoId }: Props) {
  const queryClient = useQueryClient()
  const [renglonAbiertoId, setRenglonAbiertoId] = useState<string | null>(null)

  const queryKey = ['proceso-matching', procesoId] as const
  const matchingQuery = useQuery({
    queryKey,
    queryFn: () => obtenerMatchingProceso(procesoId),
  })

  async function alDecidir() {
    setRenglonAbiertoId(null)
    await queryClient.invalidateQueries({ queryKey })
  }

  const confirmarMutation = useMutation({
    mutationFn: ({ itemId, productoId }: { itemId: string; productoId: string }) =>
      confirmarMatching(itemId, productoId),
    onSuccess: alDecidir,
  })

  const sinMatchMutation = useMutation({
    mutationFn: (itemId: string) => marcarSinMatch(itemId),
    onSuccess: alDecidir,
  })

  const isPending = confirmarMutation.isPending || sinMatchMutation.isPending
  const errorMutacion = confirmarMutation.error ?? sinMatchMutation.error

  // A new decision clears the error of a previous failed one.
  function confirmar(itemId: string, productoId: string) {
    sinMatchMutation.reset()
    confirmarMutation.mutate({ itemId, productoId })
  }

  function sinMatch(itemId: string) {
    confirmarMutation.reset()
    sinMatchMutation.mutate(itemId)
  }

  if (matchingQuery.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando matching…</div>
  }

  if (matchingQuery.isError || !matchingQuery.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {matchingQuery.error instanceof Error
          ? matchingQuery.error.message
          : 'No se pudo cargar el matching de este proceso.'}
      </div>
    )
  }

  const matching = matchingQuery.data
  const pendientes = matching.renglones.filter((r) => r.estado_matching === 'pendiente').length
  const sugeridos = matching.renglones.filter((r) => r.estado_matching === 'sugerido').length
  const resueltos = matching.renglones.length - pendientes - sugeridos

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-10">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-900">Matching de {matching.nombre}</h1>
        <p className="text-sm text-slate-600">
          {[matching.cliente, CLASE_LEGIBLE[matching.clase] ?? matching.clase].filter(Boolean).join(' · ')}
        </p>
        <p className="text-sm text-slate-500">
          {[
            contar(pendientes, 'pendiente', 'pendientes'),
            contar(sugeridos, 'sugerido', 'sugeridos'),
            contar(resueltos, 'resuelto', 'resueltos'),
          ].join(' · ')}
        </p>
      </header>

      {errorMutacion && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {errorMutacion instanceof Error ? errorMutacion.message : 'No se pudo guardar el matching.'}
        </p>
      )}

      {matching.renglones.length === 0 ? (
        <p className="text-sm text-slate-500">Este proceso no tiene renglones.</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
              <th className="pb-2 pr-4">Renglón</th>
              <th className="pb-2 pr-4">Descripción</th>
              <th className="pb-2 pr-4 text-right">Cantidad</th>
              <th className="pb-2 pr-4">Estado</th>
              <th className="pb-2 pr-4">Producto</th>
              <th className="pb-2">
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {matching.renglones.map((renglon) => (
              <RenglonMatchingFila
                key={renglon.item_proceso_id}
                renglon={renglon}
                abierto={renglonAbiertoId === renglon.item_proceso_id}
                isPending={isPending}
                onAlternar={() =>
                  setRenglonAbiertoId((abierto) =>
                    abierto === renglon.item_proceso_id ? null : renglon.item_proceso_id,
                  )
                }
                onConfirmar={(productoId) => confirmar(renglon.item_proceso_id, productoId)}
                onSinMatch={() => sinMatch(renglon.item_proceso_id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
