import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth, type Rol } from '@/features/auth/AuthContext'
import { listarDroguerias } from '@/lib/api/droguerias'
import { invitarUsuario } from '@/lib/api/usuarios'

const CAMPOS_VACIOS = { email: '', nombre: '', apellido: '' }

export function InvitarUsuarioDialog({ rolesAsignables }: { rolesAsignables: Rol[] }) {
  const { perfil } = useAuth()
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState(CAMPOS_VACIOS)
  const [rol, setRol] = useState<Rol>(rolesAsignables[0])
  const [drogueriaId, setDrogueriaId] = useState('')
  const queryClient = useQueryClient()

  // Un admin invita siempre dentro de su propia droguería (el backend la
  // fuerza sola, ver crear_usuario en usuarios/service.py) — no necesita
  // elegirla. Un superadmin no pertenece a ninguna, así que sí tiene que
  // elegir a cuál empresa va el usuario nuevo.
  const esSuperadmin = perfil?.rol === 'superadmin'
  const { data: droguerias } = useQuery({
    queryKey: ['droguerias'],
    queryFn: listarDroguerias,
    enabled: open && esSuperadmin,
  })

  const mutation = useMutation({
    mutationFn: () =>
      invitarUsuario({
        ...campos,
        rol,
        ...(esSuperadmin ? { drogueria_id: drogueriaId } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setOpen(false)
      setCampos(CAMPOS_VACIOS)
      setDrogueriaId('')
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white"
        >
          + Invitar usuario
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            Invitar usuario
          </Dialog.Title>
          <p className="mt-1 text-xs text-slate-500">
            Se le envía un email para que defina su propia contraseña.
          </p>

          <form
            className="mt-4 space-y-4"
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

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Rol</span>
              <select
                value={rol}
                onChange={(event) => setRol(event.target.value as Rol)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                {rolesAsignables.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>

            {esSuperadmin && (
              <label className="block text-sm">
                <span className="mb-1 block text-slate-600">Empresa</span>
                <select
                  required
                  value={drogueriaId}
                  onChange={(event) => setDrogueriaId(event.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="" disabled>
                    Elegir empresa…
                  </option>
                  {droguerias?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nombre}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {mutation.isError && (
              <p className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo invitar.'}
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
                {mutation.isPending ? 'Invitando…' : 'Invitar'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
