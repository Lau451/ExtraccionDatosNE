import * as Dialog from '@radix-ui/react-dialog'

/** Reemplaza window.confirm() — bloquea el hilo del navegador (rompe
 * automatización con Chrome DevTools Protocol) y no se puede estilizar. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  confirmLabel = 'Eliminar',
  pendingLabel = 'Eliminando…',
  isPending = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  onConfirm: () => void
  confirmLabel?: string
  /** Texto del botón mientras `isPending`. Default retrocompatible con el único
   * uso previo (eliminar usuario) — otros callers (validar-extraccion) lo
   * parametrizan porque "Eliminando…" no tiene sentido para confirmar una
   * validación. */
  pendingLabel?: string
  isPending?: boolean
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-slate-600">
            {description}
          </Dialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <button type="button" className="rounded-md px-3 py-2 text-sm text-slate-600">
                Cancelar
              </button>
            </Dialog.Close>
            <button
              type="button"
              disabled={isPending}
              onClick={onConfirm}
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {isPending ? pendingLabel : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
