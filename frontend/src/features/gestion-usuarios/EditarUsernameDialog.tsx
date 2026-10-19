import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cambiarUsernameUsuario, type Usuario } from '@/lib/api/usuarios'
import { ERROR_USERNAME, mensajeDeError, normalizarUsername, usernameValido } from './credenciales'

/** Edición del nombre de usuario (spec S5): los usuarios migrados recibieron
 * uno derivado del email, y el admin lo puede corregir. La unicidad la
 * controla el backend (409). */
export function EditarUsernameDialog({ usuario, onClose }: { usuario: Usuario | null; onClose: () => void }) {
  return (
    <Dialog.Root open={usuario !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          {/* key: el formulario arranca con el username de cada usuario. */}
          {usuario && <FormularioUsername key={usuario.id} usuario={usuario} onClose={onClose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function FormularioUsername({ usuario, onClose }: { usuario: Usuario; onClose: () => void }) {
  const [username, setUsername] = useState(usuario.username)
  const [errorValidacion, setErrorValidacion] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => cambiarUsernameUsuario(usuario.id, normalizarUsername(username)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      onClose()
    },
  })

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setErrorValidacion(null)
    if (!usernameValido(normalizarUsername(username))) {
      setErrorValidacion(ERROR_USERNAME)
      return
    }
    mutation.mutate()
  }

  const error =
    errorValidacion ?? (mutation.isError ? mensajeDeError(mutation.error, 'No se pudo cambiar el usuario.') : null)

  return (
    <>
      <Dialog.Title className="text-base font-semibold text-slate-900">Editar usuario</Dialog.Title>
      <Dialog.Description className="mt-1 text-xs text-slate-500">
        Nombre de usuario con el que {usuario.nombre} {usuario.apellido ?? ''} ingresa al sistema.
      </Dialog.Description>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">Usuario</span>
          <input
            required
            autoCapitalize="none"
            autoComplete="off"
            value={username}
            onChange={(event) => setUsername(event.target.value.toLowerCase())}
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
            {mutation.isPending ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </form>
    </>
  )
}
