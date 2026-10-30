import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { blanquearPasswordUsuario, type Usuario } from '@/lib/api/usuarios'
import { ERROR_PASSWORD_TEMPORAL, PASSWORD_TEMPORAL_MINIMO, mensajeDeError } from './credenciales'

/** Blanqueo por el admin (spec S4): no hay recuperación por email, el usuario
 * le pide al admin una contraseña temporal nueva y la cambia al ingresar. */
export function BlanquearPasswordDialog({ usuario, onClose }: { usuario: Usuario | null; onClose: () => void }) {
  return (
    <Dialog.Root open={usuario !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed z-50 inset-0 bg-black/40" />
        <Dialog.Content className="fixed z-50 top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          {/* key: el formulario arranca vacío para cada usuario. */}
          {usuario && <FormularioBlanqueo key={usuario.id} usuario={usuario} onClose={onClose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function FormularioBlanqueo({ usuario, onClose }: { usuario: Usuario; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [errorValidacion, setErrorValidacion] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => blanquearPasswordUsuario(usuario.id, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      onClose()
    },
  })

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setErrorValidacion(null)
    if (password.length < PASSWORD_TEMPORAL_MINIMO) {
      setErrorValidacion(ERROR_PASSWORD_TEMPORAL)
      return
    }
    mutation.mutate()
  }

  const error =
    errorValidacion ?? (mutation.isError ? mensajeDeError(mutation.error, 'No se pudo blanquear la contraseña.') : null)

  return (
    <>
      <Dialog.Title className="text-base font-semibold text-slate-900">Blanquear contraseña</Dialog.Title>
      <Dialog.Description className="mt-1 text-xs text-slate-500">
        Pasale a {usuario.nombre} {usuario.apellido ?? ''} ({usuario.username}) la contraseña temporal
        nueva. Se le va a pedir que la cambie en el próximo ingreso.
      </Dialog.Description>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">Contraseña temporal nueva</span>
          <input
            required
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

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
            {mutation.isPending ? 'Blanqueando…' : 'Blanquear'}
          </button>
        </div>
      </form>
    </>
  )
}
