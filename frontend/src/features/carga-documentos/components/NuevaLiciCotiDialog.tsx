import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  crearProcesoComercial,
  type Clase,
  type Modalidad,
  type ProcesoComercialResumen,
} from '@/lib/api/procesosComerciales'

interface Props {
  onCreated: (proceso: ProcesoComercialResumen) => void
}

export function NuevaLiciCotiDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false)
  const [nombre, setNombre] = useState('')
  const [clase, setClase] = useState<Clase>('cotizacion')
  const [apertura, setApertura] = useState('')
  const [modalidad, setModalidad] = useState<Modalidad>('mail')
  const queryClient = useQueryClient()

  const esLicitacion = clase === 'licitacion'

  const mutation = useMutation({
    mutationFn: () =>
      crearProcesoComercial({
        nombre,
        clase,
        // El backend rechaza apertura/modalidad para clase=cotizacion (constraint
        // ck_proc_cotizacion_sin_seguimiento) — solo se mandan si es licitación.
        ...(esLicitacion && apertura ? { apertura } : {}),
        ...(esLicitacion ? { modalidad } : {}),
      }),
    onSuccess: (proceso) => {
      queryClient.invalidateQueries({ queryKey: ['procesos-comerciales'] })
      onCreated(proceso)
      setOpen(false)
      setNombre('')
      setApertura('')
      setClase('cotizacion')
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="text-sm font-medium text-accent hover:underline">
          + Nueva
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            Nueva licitación / cotización
          </Dialog.Title>

          <form
            className="mt-4 space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Nombre</span>
              <input
                required
                value={nombre}
                onChange={(event) => setNombre(event.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Tipo</span>
              <select
                value={clase}
                onChange={(event) => setClase(event.target.value as Clase)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="cotizacion">Cotización</option>
                <option value="licitacion">Licitación</option>
              </select>
            </label>

            {esLicitacion && (
              <>
                <label className="block text-sm">
                  <span className="mb-1 block text-slate-600">Apertura</span>
                  <input
                    type="date"
                    value={apertura}
                    onChange={(event) => setApertura(event.target.value)}
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  />
                </label>

                <label className="block text-sm">
                  <span className="mb-1 block text-slate-600">Modalidad</span>
                  <select
                    value={modalidad}
                    onChange={(event) => setModalidad(event.target.value as Modalidad)}
                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  >
                    <option value="mail">Mail</option>
                    <option value="pliego">Pliego</option>
                  </select>
                </label>
              </>
            )}

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
