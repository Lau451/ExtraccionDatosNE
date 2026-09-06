import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  actualizarCondicionPago,
  crearCondicionPago,
  listarCondicionesPago,
  type CondicionPagoUpdatePayload,
} from '@/lib/api/catalogosComerciales'

function parsearPlazos(texto: string): number[] | undefined {
  const valores = texto
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v !== '')
    .map((v) => Number(v))
    .filter((v) => Number.isFinite(v))
  return valores.length > 0 ? valores : undefined
}

/** Catálogo de apoyo para condición de pago habitual de un rol cliente o
 * proveedor — mismo criterio que `GestionCategoriasDialog` en productos. */
export function GestionCondicionesPagoDialog({ puedeEscribir }: { puedeEscribir: boolean }) {
  const [open, setOpen] = useState(false)
  const [nombreNuevo, setNombreNuevo] = useState('')
  const [plazosNuevo, setPlazosNuevo] = useState('')
  const [descripcionNueva, setDescripcionNueva] = useState('')
  const queryClient = useQueryClient()

  const { data: condiciones, isPending } = useQuery({
    queryKey: ['condiciones-pago'],
    queryFn: listarCondicionesPago,
    enabled: open,
  })

  const crearMutation = useMutation({
    mutationFn: () =>
      crearCondicionPago({
        nombre: nombreNuevo,
        plazos_dias: parsearPlazos(plazosNuevo),
        descripcion: descripcionNueva || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['condiciones-pago'] })
      setNombreNuevo('')
      setPlazosNuevo('')
      setDescripcionNueva('')
    },
  })

  const actualizarMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CondicionPagoUpdatePayload }) =>
      actualizarCondicionPago(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['condiciones-pago'] }),
  })

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
        >
          Condiciones de pago
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            Condiciones de pago
          </Dialog.Title>

          {isPending ? (
            <p className="mt-4 text-sm text-slate-500">Cargando…</p>
          ) : (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 font-medium">Nombre</th>
                  <th className="py-2 font-medium">Plazos (días)</th>
                  <th className="py-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {condiciones?.map((condicion) => (
                  <tr key={condicion.id} className="border-b border-slate-100">
                    <td className="py-2">{condicion.nombre}</td>
                    <td className="py-2 text-slate-500">
                      {condicion.plazos_dias.length > 0 ? condicion.plazos_dias.join(', ') : '—'}
                    </td>
                    <td className="py-2">
                      {puedeEscribir ? (
                        <button
                          type="button"
                          onClick={() =>
                            actualizarMutation.mutate({
                              id: condicion.id,
                              payload: { activo: !condicion.activo },
                            })
                          }
                          className="text-sm font-medium text-accent hover:underline"
                        >
                          {condicion.activo ? 'Desactivar' : 'Reactivar'}
                        </button>
                      ) : (
                        <span className={condicion.activo ? 'text-emerald-600' : 'text-slate-400'}>
                          {condicion.activo ? 'Activa' : 'Inactiva'}
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
                <span className="mb-1 block text-slate-600">Plazos (días, separados por coma)</span>
                <input
                  value={plazosNuevo}
                  onChange={(event) => setPlazosNuevo(event.target.value)}
                  placeholder="30, 60, 90"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
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
