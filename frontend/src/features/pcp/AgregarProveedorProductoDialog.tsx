import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { agregarProveedorProducto } from '@/lib/api/pcp'
import type { Tercero } from '@/lib/api/terceros'
import { pcpQueryKeys } from './queryKeys'

export function AgregarProveedorProductoDialog({
  productoId,
  proveedores,
}: {
  productoId: string
  proveedores: Tercero[]
}) {
  const [open, setOpen] = useState(false)
  const [proveedorId, setProveedorId] = useState('')
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => agregarProveedorProducto(productoId, { proveedor_id: proveedorId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.proveedoresProducto(productoId) })
      setOpen(false)
      setProveedorId('')
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white active:scale-[0.96]">Agregar proveedor</button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-navy">Asociar proveedor</Dialog.Title>
          <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
            <label className="block text-sm text-slate-600">
              Proveedor
              <select aria-label="Proveedor" required value={proveedorId} onChange={(event) => setProveedorId(event.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2">
                <option value="">Seleccioná un proveedor</option>
                {proveedores.map((proveedor) => <option key={proveedor.id} value={proveedor.id}>{proveedor.razon_social}</option>)}
              </select>
            </label>
            {mutation.isError ? <p role="alert" className="text-sm text-red-600">{mutation.error instanceof Error ? mutation.error.message : 'No se pudo asociar el proveedor.'}</p> : null}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild><button type="button" className="min-h-10 px-3 text-sm text-slate-600">Cancelar</button></Dialog.Close>
              <button type="submit" disabled={!proveedorId || mutation.isPending} className="min-h-10 rounded-md bg-navy px-3 text-sm font-medium text-white disabled:opacity-50">{mutation.isPending ? 'Asociando…' : 'Asociar'}</button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
