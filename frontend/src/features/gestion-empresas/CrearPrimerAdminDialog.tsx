import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { crearUsuario } from '@/lib/api/usuarios'
import {
  ERROR_PASSWORD_TEMPORAL,
  ERROR_USERNAME,
  PASSWORD_TEMPORAL_MINIMO,
  mensajeDeError,
  normalizarUsername,
  usernameValido,
} from '@/features/gestion-usuarios/credenciales'

const CAMPOS_VACIOS = { username: '', password: '', nombre: '', apellido: '' }

export function CrearPrimerAdminDialog({
  drogueriaId,
  drogueriaNombre,
}: {
  drogueriaId: string
  drogueriaNombre: string
}) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState(CAMPOS_VACIOS)
  const [errorValidacion, setErrorValidacion] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () =>
      crearUsuario({
        ...campos,
        username: normalizarUsername(campos.username),
        rol: 'admin',
        drogueria_id: drogueriaId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setOpen(false)
      setCampos(CAMPOS_VACIOS)
    },
  })

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setErrorValidacion(null)
    if (!usernameValido(normalizarUsername(campos.username))) {
      setErrorValidacion(ERROR_USERNAME)
      return
    }
    if (campos.password.length < PASSWORD_TEMPORAL_MINIMO) {
      setErrorValidacion(ERROR_PASSWORD_TEMPORAL)
      return
    }
    mutation.mutate()
  }

  const error = errorValidacion ?? (mutation.isError ? mensajeDeError(mutation.error, 'No se pudo crear.') : null)

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
          <Dialog.Description className="mt-1 text-xs text-slate-500">
            Pasale al usuario su nombre de usuario y la contraseña temporal. Se le va a pedir que la
            cambie en el primer ingreso.
          </Dialog.Description>

          <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Usuario</span>
              <input
                required
                autoCapitalize="none"
                autoComplete="off"
                value={campos.username}
                onChange={(event) =>
                  setCampos((c) => ({ ...c, username: event.target.value.toLowerCase() }))
                }
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Contraseña temporal</span>
              <input
                required
                autoComplete="new-password"
                value={campos.password}
                onChange={(event) => setCampos((c) => ({ ...c, password: event.target.value }))}
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
                {mutation.isPending ? 'Creando…' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
