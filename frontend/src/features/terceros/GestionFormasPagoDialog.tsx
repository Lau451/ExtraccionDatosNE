import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  actualizarFormaPago,
  crearFormaPago,
  listarFormasPago,
  type FormaPagoUpdatePayload,
  type TipoFormaPago,
} from '@/lib/api/catalogosComerciales'

const TIPOS_FORMA_PAGO: TipoFormaPago[] = [
  'transferencia',
  'cheque',
  'echeq',
  'efectivo',
  'deposito',
  'otro',
]

/** Catálogo de apoyo para forma de pago habitual de un rol cliente o
 * proveedor — mismo criterio que `GestionCategoriasDialog` en productos. */
export function GestionFormasPagoDialog({ puedeEscribir }: { puedeEscribir: boolean }) {
  const [open, setOpen] = useState(false)
  const [nombreNuevo, setNombreNuevo] = useState('')
  const [tipoNuevo, setTipoNuevo] = useState<TipoFormaPago>('transferencia')
  const [descripcionNueva, setDescripcionNueva] = useState('')
  const queryClient = useQueryClient()

  const { data: formas, isPending } = useQuery({
    queryKey: ['formas-pago'],
    queryFn: listarFormasPago,
    enabled: open,
  })

  const crearMutation = useMutation({
    mutationFn: () =>
      crearFormaPago({
        nombre: nombreNuevo,
        tipo: tipoNuevo,
        descripcion: descripcionNueva || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['formas-pago'] })
      setNombreNuevo('')
      setTipoNuevo('transferencia')
      setDescripcionNueva('')
    },
  })

  const actualizarMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: FormaPagoUpdatePayload }) =>
      actualizarFormaPago(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['formas-pago'] }),
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
        >
          Formas de pago
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">Formas de pago</Dialog.Title>

          {isPending ? (
            <p className="mt-4 text-sm text-slate-500">Cargando…</p>
          ) : (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 font-medium">Nombre</th>
                  <th className="py-2 font-medium">Tipo</th>
                  <th className="py-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {formas?.map((forma) => (
                  <tr key={forma.id} className="border-b border-slate-100">
                    <td className="py-2">{forma.nombre}</td>
                    <td className="py-2 text-slate-500">{forma.tipo}</td>
                    <td className="py-2">
                      {puedeEscribir ? (
                        <button
                          type="button"
                          onClick={() =>
                            actualizarMutation.mutate({
                              id: forma.id,
                              payload: { activo: !forma.activo },
                            })
                          }
                          className="text-sm font-medium text-accent hover:underline"
                        >
                          {forma.activo ? 'Desactivar' : 'Reactivar'}
                        </button>
                      ) : (
                        <span className={forma.activo ? 'text-emerald-600' : 'text-slate-400'}>
                          {forma.activo ? 'Activa' : 'Inactiva'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {puedeEscribir && (
            <form
              className="mt-4 flex items-end gap-2 border-t border-slate-200 pt-4"
              onSubmit={(event) => {
                event.preventDefault()
                crearMutation.mutate()
              }}
            >
              <label className="flex-1 text-sm">
                <span className="mb-1 block text-slate-600">Nombre</span>
                <input
                  required
                  value={nombreNuevo}
                  onChange={(event) => setNombreNuevo(event.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="flex-1 text-sm">
                <span className="mb-1 block text-slate-600">Tipo</span>
                <select
                  value={tipoNuevo}
                  onChange={(event) => setTipoNuevo(event.target.value as TipoFormaPago)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                >
                  {TIPOS_FORMA_PAGO.map((tipo) => (
                    <option key={tipo} value={tipo}>
                      {tipo}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex-1 text-sm">
                <span className="mb-1 block text-slate-600">Descripción</span>
                <input
                  value={descripcionNueva}
                  onChange={(event) => setDescripcionNueva(event.target.value)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
              <button
                type="submit"
                disabled={crearMutation.isPending}
                className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {crearMutation.isPending ? 'Creando…' : 'Agregar'}
              </button>
            </form>
          )}

          {(crearMutation.isError || actualizarMutation.isError) && (
            <p className="mt-2 text-sm text-red-600">No se pudo aplicar el cambio.</p>
          )}

          <div className="mt-4 flex justify-end">
            <Dialog.Close asChild>
              <button type="button" className="rounded-md px-3 py-2 text-sm text-slate-600">
                Cerrar
              </button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
