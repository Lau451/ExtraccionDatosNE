import { useEffect, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { actualizarTercero, type Tercero, type TerceroUpdatePayload } from '@/lib/api/terceros'

type CamposApp = Required<TerceroUpdatePayload>

function camposDesdeTercero(tercero: Tercero): CamposApp {
  return {
    nombre_fantasia: tercero.nombre_fantasia ?? '',
    email: tercero.email ?? '',
    telefono: tercero.telefono ?? '',
    sitio_web: tercero.sitio_web ?? '',
    notas: tercero.notas ?? '',
  }
}

/** Edición de los datos propios de la app. Razón social, código interno, CUIT
 * y estado son de Progress (docs/arquitectura/maestros-progress.md): se
 * muestran de solo lectura y no viajan en el PATCH. */
export function EditarTerceroDialog({ tercero, trigger }: { tercero: Tercero; trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState<CamposApp>(camposDesdeTercero(tercero))
  const queryClient = useQueryClient()

  useEffect(() => {
    if (open) {
      setCampos(camposDesdeTercero(tercero))
    }
  }, [open, tercero])

  function limpiarPayload(): TerceroUpdatePayload {
    return {
      nombre_fantasia: campos.nombre_fantasia || undefined,
      email: campos.email || undefined,
      telefono: campos.telefono || undefined,
      sitio_web: campos.sitio_web || undefined,
      notas: campos.notas || undefined,
    }
  }

  const mutation = useMutation({
    mutationFn: () => actualizarTercero(tercero.id, limpiarPayload()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros'] })
      queryClient.invalidateQueries({ queryKey: ['terceros', tercero.id] })
      setOpen(false)
    },
  })

  function campo(key: keyof CamposApp, label: string, type = 'text') {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">{label}</span>
        <input
          type={type}
          value={campos[key]}
          onChange={(event) => setCampos((c) => ({ ...c, [key]: event.target.value }))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed z-50 inset-0 bg-black/40" />
        <Dialog.Content className="fixed z-50 top-1/2 left-1/2 max-h-[85vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">Editar tercero</Dialog.Title>

          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 rounded-md bg-slate-50 p-3 text-sm">
            <DatoProgress etiqueta="Razón social" valor={tercero.razon_social} />
            <DatoProgress etiqueta="Código interno" valor={tercero.codigo_interno} />
            <DatoProgress etiqueta="CUIT" valor={tercero.cuit} />
            <DatoProgress etiqueta="Estado" valor={tercero.activo ? 'Activo' : 'Inactivo'} />
          </dl>
          <p className="mt-2 text-xs text-slate-500">Estos datos vienen de Progress.</p>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            {campo('nombre_fantasia', 'Nombre de fantasía')}
            {campo('email', 'Email', 'email')}
            {campo('telefono', 'Teléfono')}
            {campo('sitio_web', 'Sitio web')}

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Notas</span>
              <textarea
                value={campos.notas}
                onChange={(event) => setCampos((c) => ({ ...c, notas: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                rows={3}
              />
            </label>

            {mutation.isError && (
              <p className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo guardar.'}
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
                {mutation.isPending ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function DatoProgress({ etiqueta, valor }: { etiqueta: string; valor: string | null }) {
  return (
    <div>
      <dt className="text-slate-500">{etiqueta}</dt>
      <dd className="text-slate-800">{valor || '—'}</dd>
    </div>
  )
}
