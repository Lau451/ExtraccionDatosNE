import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { invitarUsuario } from '@/lib/api/usuarios'

const CAMPOS_VACIOS = { email: '', nombre: '', apellido: '' }

export function CrearPrimerAdminDialog({
  drogueriaId,
  drogueriaNombre,
}: {
  drogueriaId: string
  drogueriaNombre: string
}) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState(CAMPOS_VACIOS)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () =>
      invitarUsuario({ ...campos, rol: 'admin', drogueria_id: drogueriaId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setOpen(false)
      setCampos(CAMPOS_VACIOS)
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="text-sm font-medium text-accent hover:underline">
          Crear admin
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            Crear admin para {drogueriaNombre}
          </Dialog.Title>
          <p className="mt-1 text-xs text-slate-500">
            Se le envía un email para que defina su propia contraseña.
          </p>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Email</span>
              <input
                type="email"
                required
                value={campos.email}
                onChange={(event) => setCampos((c) => ({ ...c, email: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Nombre</span>
              <input
                required
                value={campos.nombre}
                onChange={(event) => setCampos((c) => ({ ...c, nombre: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Apellido</span>
              <input
                required
                value={campos.apellido}
                onChange={(event) => setCampos((c) => ({ ...c, apellido: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            {mutation.isError && (
              <p className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo crear.'}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close asChild>
                <button type="button" className="rounded-md px-3 py-2 text-sm text-slate-600">
                  Cancelar
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={mutation.isPending}
                className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {mutation.isPending ? 'Creando…' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
