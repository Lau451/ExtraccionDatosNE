import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cerrarPcp, type Pcp } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function CerrarPcpDialog({ pcpId }: { pcpId: string }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => cerrarPcp(pcpId),
    onSuccess: (actualizado) => {
      queryClient.setQueryData(pcpQueryKeys.detalle(pcpId), actualizado)
      queryClient.setQueriesData<Pcp[]>({ queryKey: pcpQueryKeys.listas() }, (pcps) =>
        Array.isArray(pcps) ? pcps.map((pcp) => (pcp.id === pcpId ? actualizado : pcp)) : pcps,
      )
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.renglones(pcpId), refetchType: 'none' })
      queryClient.invalidateQueries({ queryKey: ['pcp', 'sugerencias'] })
      setOpen(false)
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild><button type="button" className="min-h-10 rounded-md bg-red-700 px-3 text-sm font-medium text-white active:scale-[0.96]">Cerrar PCP</button></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">Cerrar PCP</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-slate-600">Esta acción finaliza el PCP y sus recursos relacionados.</Dialog.Description>
          {mutation.isError ? <p role="alert" className="mt-3 text-sm text-red-600">No se pudo cerrar el PCP.</p> : null}
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild><button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button></Dialog.Close>
            <button type="button" onClick={() => mutation.mutate()} disabled={mutation.isPending} className="min-h-10 rounded-md bg-red-700 px-3 text-sm font-medium text-white disabled:opacity-50">
              {mutation.isPending ? 'Cerrando…' : 'Confirmar cierre'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
