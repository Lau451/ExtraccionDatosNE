import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { crearLicitacion, type LicitacionActiva, type TipoLicitacion } from '@/lib/api/extraccion'

const TIPOS: TipoLicitacion[] = ['descartables', 'medicamentos', 'soluciones', 'panales', 'formulas']

interface Props {
  onCreated: (licitacion: LicitacionActiva) => void
}

export function NuevaLicitacionDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false)
  const [nombre, setNombre] = useState('')
  const [tipo, setTipo] = useState<TipoLicitacion>('descartables')
  const [apertura, setApertura] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => crearLicitacion({ nombre, tipo, apertura }),
    onSuccess: (licitacion) => {
      queryClient.invalidateQueries({ queryKey: ['licitaciones-activas'] })
      onCreated(licitacion)
      setOpen(false)
      setNombre('')
      setApertura('')
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
            Nueva licitación
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
                value={tipo}
                onChange={(event) => setTipo(event.target.value as TipoLicitacion)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                {TIPOS.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Apertura</span>
              <input
                required
                type="date"
                value={apertura}
                onChange={(event) => setApertura(event.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            {mutation.isError && (
              <p className="text-sm text-red-600">No se pudo crear la licitación.</p>
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
