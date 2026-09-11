import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { agruparConsultas, type SeleccionParaAgrupar } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

/**
 * Deliberadamente toma `puedeEscribir` como prop explícita en vez de dejar
 * que el padre la monte condicionalmente (a diferencia de
 * `CrearRenglonDialog`/`CerrarPcpDialog`): el mismo diálogo se reutiliza
 * desde más de un punto de montaje elegible (flujo de renglón y, más
 * adelante, PCP), así que centraliza el chequeo de rol una sola vez
 * (design.md, decisión documentada en apply-progress.md Work Unit 6.1).
 */
export function AgruparConsultaDialog({
  pcpId,
  selecciones,
  puedeEscribir,
}: {
  pcpId: string
  selecciones: SeleccionParaAgrupar[]
  puedeEscribir: boolean
}) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => agruparConsultas({ selecciones }),
    onSuccess: (consultas) => {
      consultas.forEach((consulta) => {
        queryClient.setQueryData(pcpQueryKeys.consulta(consulta.id), consulta)
      })
      // Las selecciones recién agrupadas ya no deberían seguir ofreciéndose
      // para un nuevo agrupamiento -- sin esto, seleccionesAgrupablesQuery
      // (cacheada en PcpDetalle) sigue mostrando el mismo listado y permite
      // enviar un duplicado sin recargar la página.
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.seleccionesAgrupables(pcpId) })
    },
  })

  if (!puedeEscribir) return null

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white active:scale-[0.96]">Agrupar consulta</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">Agrupar consulta</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-slate-600">
            Se agruparán {selecciones.length} selección(es) en una consulta por proveedor.
          </Dialog.Description>
          {mutation.isError ? <p role="alert" className="mt-3 text-sm text-red-600">No se pudo agrupar la consulta.</p> : null}
          {mutation.isSuccess ? (
            <ul className="mt-3 space-y-1 text-sm">
              {mutation.data.map((consulta) => (
                <li key={consulta.id}>
                  <a href={`/pcp/consultas/${consulta.id}`} className="text-accent hover:underline">Ver consulta de {consulta.proveedor_id}</a>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild><button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button></Dialog.Close>
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || selecciones.length === 0}
              className="min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50"
            >
              {mutation.isPending ? 'Agrupando…' : 'Confirmar'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
