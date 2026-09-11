import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { crearRenglon } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

export function CrearRenglonDialog({ pcpId }: { pcpId: string }) {
  const [open, setOpen] = useState(false)
  const [itemProcesoId, setItemProcesoId] = useState('')
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => crearRenglon(pcpId, { item_proceso_id: itemProcesoId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.renglones(pcpId) })
      setOpen(false)
      setItemProcesoId('')
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white active:scale-[0.96]">Nuevo renglón</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">Nuevo renglón</Dialog.Title>
          <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
            <label className="block text-sm text-slate-600">
              ID de ítem de proceso
              <input
                type="text"
                required
                value={itemProcesoId}
                onChange={(event) => setItemProcesoId(event.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
              />
            </label>
            {mutation.isError ? <p role="alert" className="text-sm text-red-600">{mutation.error instanceof Error ? mutation.error.message : 'No se pudo crear el renglón.'}</p> : null}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild><button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button></Dialog.Close>
              <button type="submit" disabled={!itemProcesoId || mutation.isPending} className="min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50">{mutation.isPending ? 'Creando…' : 'Crear'}</button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
