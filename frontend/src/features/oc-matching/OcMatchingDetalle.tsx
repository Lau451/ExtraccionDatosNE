import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  confirmarVinculo,
  deshacerVinculo,
  descartarRenglon,
  obtenerMatching,
  obtenerPresupuestosCandidatos,
  type MatchingOut,
} from '@/lib/api/ocMatching'
import { ColumnaOrdenCompra } from './components/ColumnaOrdenCompra'
import { ColumnaPresupuesto } from './components/ColumnaPresupuesto'
import { SelectorPresupuesto } from './components/SelectorPresupuesto'

interface Props {
  ordenCompraId: string
  /** Presupuesto elegido en esta sesión, leído del search param de la ruta
   * (design.md D8). `undefined` cuando todavía no se eligió -- el servidor lo
   * resuelve (vínculos confirmados > query param > sugerido del ranking). */
  presupuestoId?: string
}

/** Container de la pantalla de matching (design.md § Forma del frontend, D12,
 * D13): 2 queries (`presupuestos-candidatos`, `matching`), 3 mutaciones
 * (confirmar/deshacer/descartar). El único estado local es el renglón de OC
 * resaltado -- el presupuesto elegido NO es estado local (D8, alternativa
 * (b) rechazada): vive en la URL, y este componente lo sincroniza navegando.
 * Cada mutación reemplaza la cache con el `MatchingOut` completo que devuelve
 * (D13): sin refetch por click. */
export function OcMatchingDetalle({ ordenCompraId, presupuestoId }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [renglonSeleccionadoId, setRenglonSeleccionadoId] = useState<string | null>(null)

  const candidatosQuery = useQuery({
    queryKey: ['oc-matching', ordenCompraId, 'presupuestos-candidatos'],
    queryFn: () => obtenerPresupuestosCandidatos(ordenCompraId),
  })

  const matchingQueryKey = ['oc-matching', ordenCompraId, 'matching', presupuestoId ?? null] as const
  const matchingQuery = useQuery({
    queryKey: matchingQueryKey,
    queryFn: () => obtenerMatching(ordenCompraId, presupuestoId),
  })

  function reemplazarCache(resultado: MatchingOut) {
    queryClient.setQueryData(matchingQueryKey, resultado)
  }

  const confirmarMutation = useMutation({
    mutationFn: ({ ocItemId, presupuestoItemId }: { ocItemId: string; presupuestoItemId: string }) =>
      confirmarVinculo(ordenCompraId, ocItemId, presupuestoItemId),
    onSuccess: reemplazarCache,
  })

  const deshacerMutation = useMutation({
    mutationFn: (ocItemId: string) => deshacerVinculo(ordenCompraId, ocItemId),
    onSuccess: reemplazarCache,
  })

  const descartarMutation = useMutation({
    mutationFn: (ocItemId: string) => descartarRenglon(ordenCompraId, ocItemId),
    onSuccess: reemplazarCache,
  })

  const isPending =
    confirmarMutation.isPending || deshacerMutation.isPending || descartarMutation.isPending

  function elegirPresupuesto(id: string) {
    navigate({
      to: '/ordenes-compra/$ordenCompraId/matching',
      params: { ordenCompraId },
      search: (previo: Record<string, unknown>) => ({ ...previo, presupuesto: id }),
      replace: true,
    })
  }

  if (matchingQuery.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando matching…</div>
  }

  if (matchingQuery.isError || !matchingQuery.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {matchingQuery.error instanceof Error
          ? matchingQuery.error.message
          : 'No se pudo cargar el matching de esta orden de compra.'}
      </div>
    )
  }

  const matching = matchingQuery.data
  const renglonSeleccionado =
    matching.renglones_oc.find((renglon) => renglon.oc_item_id === renglonSeleccionadoId) ?? null

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-10">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-900">
          Matching de orden de compra {matching.numero_oc}
        </h1>
        {matching.advertencias.map((advertencia) => (
          <p key={advertencia} className="text-sm text-amber-600">
            {advertencia}
          </p>
        ))}
      </header>

      {candidatosQuery.data && (
        <SelectorPresupuesto
          data={candidatosQuery.data}
          presupuestoIdSeleccionado={matching.presupuesto_id}
          onSeleccionar={elegirPresupuesto}
        />
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <ColumnaPresupuesto
          renglones={matching.renglones_presupuesto}
          renglonOcSeleccionado={renglonSeleccionado}
        />
        <ColumnaOrdenCompra
          renglones={matching.renglones_oc}
          renglonSeleccionadoId={renglonSeleccionadoId}
          isPending={isPending}
          onSeleccionar={setRenglonSeleccionadoId}
          onConfirmar={(ocItemId, presupuestoItemId) =>
            confirmarMutation.mutate({ ocItemId, presupuestoItemId })
          }
          onDeshacer={(ocItemId) => deshacerMutation.mutate(ocItemId)}
          onDescartar={(ocItemId) => descartarMutation.mutate(ocItemId)}
        />
      </div>
    </div>
  )
}
