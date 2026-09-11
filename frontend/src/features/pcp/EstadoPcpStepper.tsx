import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cambiarEstadoPcp, type EstadoPcp, type Pcp } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

const ETAPAS: EstadoPcp[] = ['nueva', 'en_gestion', 'esperando_respuesta', 'cerrada']
const SIGUIENTE: Record<EstadoPcp, EstadoPcp | null> = {
  nueva: 'en_gestion', en_gestion: 'esperando_respuesta', esperando_respuesta: 'cerrada', cerrada: null,
}
const ETIQUETAS: Record<EstadoPcp, string> = {
  nueva: 'Nueva', en_gestion: 'En gestión', esperando_respuesta: 'Esperando respuesta', cerrada: 'Cerrada',
}

export function EstadoPcpStepper({ pcp, puedeEscribir }: { pcp: Pcp; puedeEscribir: boolean }) {
  const queryClient = useQueryClient()
  const siguiente = SIGUIENTE[pcp.estado]
  const etapaActual = ETAPAS.indexOf(pcp.estado)
  const mutation = useMutation({
    mutationFn: (estado: EstadoPcp) => cambiarEstadoPcp(pcp.id, estado),
    onSuccess: (actualizado) => {
      queryClient.setQueryData(pcpQueryKeys.detalle(pcp.id), actualizado)
      queryClient.setQueriesData<Pcp[]>({ queryKey: pcpQueryKeys.listas() }, (pcps) =>
        Array.isArray(pcps) ? pcps.map((p) => (p.id === pcp.id ? actualizado : p)) : pcps,
      )
    },
  })

  return (
    <section aria-label="Estado del PCP" className="rounded-lg bg-slate-50 p-4">
      <ol aria-label="Etapas del PCP" className="grid gap-2 sm:grid-cols-4">
        {ETAPAS.map((etapa, indice) => {
          const estadoEtapa = indice < etapaActual ? 'completada' : indice === etapaActual ? 'actual' : 'pendiente'
          const estiloEtapa = estadoEtapa === 'completada'
            ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
            : estadoEtapa === 'actual'
              ? 'border-navy bg-white text-navy shadow-sm'
              : 'border-slate-200 bg-white text-slate-500'

          return (
            <li
              key={etapa}
              aria-current={estadoEtapa === 'actual' ? 'step' : undefined}
              aria-label={`${ETIQUETAS[etapa]} — ${estadoEtapa}`}
              className={`rounded-md border px-3 py-2 text-sm ${estiloEtapa}`}
            >
              <span className="block font-medium">{ETIQUETAS[etapa]}</span>
              <span className="block text-xs">{estadoEtapa}</span>
            </li>
          )
        })}
      </ol>
      {puedeEscribir && siguiente ? (
        <button type="button" onClick={() => mutation.mutate(siguiente)} disabled={mutation.isPending}
          className="mt-3 min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50">
          {mutation.isPending ? 'Actualizando…' : `Avanzar a ${ETIQUETAS[siguiente]}`}
        </button>
      ) : null}
      {mutation.isError ? <p role="alert" className="mt-2 text-sm text-red-600">No se pudo actualizar el estado.</p> : null}
    </section>
  )
}
