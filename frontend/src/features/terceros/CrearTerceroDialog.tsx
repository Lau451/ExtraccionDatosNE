import { useEffect, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  actualizarTercero,
  crearTercero,
  type Tercero,
  type TerceroCreatePayload,
} from '@/lib/api/terceros'

const CAMPOS_VACIOS: TerceroCreatePayload = {
  codigo_interno: '',
  razon_social: '',
  nombre_fantasia: '',
  cuit: '',
  email: '',
  telefono: '',
  sitio_web: '',
  notas: '',
}

function camposDesdeTercero(tercero: Tercero): TerceroCreatePayload {
  return {
    codigo_interno: tercero.codigo_interno ?? '',
    razon_social: tercero.razon_social,
    nombre_fantasia: tercero.nombre_fantasia ?? '',
    cuit: tercero.cuit ?? '',
    email: tercero.email ?? '',
    telefono: tercero.telefono ?? '',
    sitio_web: tercero.sitio_web ?? '',
    notas: tercero.notas ?? '',
  }
}

/** Alta o edición de un tercero — mismo criterio que `CrearProductoDialog`:
 * un único formulario para ambos casos. La creación es SOLO datos generales
 * — los roles cliente/proveedor se asignan después desde el detalle (ver
 * prompt de la tarea, punto 3). */
export function CrearTerceroDialog({
  tercero,
  trigger,
}: {
  tercero?: Tercero
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState<TerceroCreatePayload>(
    tercero ? camposDesdeTercero(tercero) : CAMPOS_VACIOS,
  )
  const queryClient = useQueryClient()
  const esEdicion = !!tercero

  useEffect(() => {
    if (open) {
      setCampos(tercero ? camposDesdeTercero(tercero) : CAMPOS_VACIOS)
    }
  }, [open, tercero])

  function limpiarPayload(): TerceroCreatePayload {
    return {
      ...campos,
      codigo_interno: campos.codigo_interno || undefined,
      nombre_fantasia: campos.nombre_fantasia || undefined,
      cuit: campos.cuit || undefined,
      email: campos.email || undefined,
      telefono: campos.telefono || undefined,
      sitio_web: campos.sitio_web || undefined,
      notas: campos.notas || undefined,
    }
  }

  const mutation = useMutation({
    mutationFn: () =>
      esEdicion ? actualizarTercero(tercero.id, limpiarPayload()) : crearTercero(limpiarPayload()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros'] })
      if (esEdicion) {
        queryClient.invalidateQueries({ queryKey: ['terceros', tercero.id] })
      }
      setOpen(false)
    },
  })

  function campo(key: keyof TerceroCreatePayload, label: string, required = false, type = 'text') {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">{label}</span>
        <input
          type={type}
          required={required}
          value={(campos[key] as string) ?? ''}
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
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 max-h-[85vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            {esEdicion ? 'Editar tercero' : 'Nuevo tercero'}
          </Dialog.Title>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            {campo('razon_social', 'Razón social', true)}
            {campo('codigo_interno', 'Código interno')}
            {campo('nombre_fantasia', 'Nombre de fantasía')}
            {campo('cuit', 'CUIT')}
            {campo('email', 'Email', false, 'email')}
            {campo('telefono', 'Teléfono')}
            {campo('sitio_web', 'Sitio web')}

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Notas</span>
              <textarea
                value={campos.notas ?? ''}
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
                {mutation.isPending ? 'Guardando…' : esEdicion ? 'Guardar' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
