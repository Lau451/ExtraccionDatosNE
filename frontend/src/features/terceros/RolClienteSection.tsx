import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { CondicionPago, FormaPago } from '@/lib/api/catalogosComerciales'
import { ApiError } from '@/lib/api/presupuestacion'
import {
  actualizarRolCliente,
  obtenerRolCliente,
  type ClienteRolUpdatePayload,
} from '@/lib/api/terceros'
import { DatoRol } from './DatoRol'

export function RolClienteSection({
  terceroId,
  condicionesPago,
  formasPago,
  puedeEscribir,
}: {
  terceroId: string
  condicionesPago: CondicionPago[]
  formasPago: FormaPago[]
  puedeEscribir: boolean
}) {
  const queryClient = useQueryClient()

  const { data: rolCliente, error, isPending } = useQuery({
    queryKey: ['terceros', terceroId, 'clientes'],
    queryFn: () => obtenerRolCliente(terceroId),
    retry: false,
  })

  const noTieneRol = error instanceof ApiError && error.status === 404

  const actualizarMutation = useMutation({
    mutationFn: (payload: ClienteRolUpdatePayload) => actualizarRolCliente(terceroId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'clientes'] }),
  })

  const [condicionPagoId, setCondicionPagoId] = useState('')
  const [formaPagoId, setFormaPagoId] = useState('')

  useEffect(() => {
    if (rolCliente) {
      setCondicionPagoId(rolCliente.condicion_pago_id ?? '')
      setFormaPagoId(rolCliente.forma_pago_id ?? '')
    }
  }, [rolCliente])

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Rol cliente</h2>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : noTieneRol ? (
        <p className="text-sm text-slate-500">
          Este tercero no tiene rol cliente asignado. El rol lo asigna Progress.
        </p>
      ) : error ? (
        <p className="text-sm text-red-600">No se pudo cargar el rol cliente.</p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            actualizarMutation.mutate({
              condicion_pago_id: condicionPagoId || undefined,
              forma_pago_id: formaPagoId || undefined,
            })
          }}
        >
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <DatoRol etiqueta="Tipo" valor={rolCliente.tipo} />
            <DatoRol etiqueta="Estado" valor={rolCliente.activo ? 'Activo' : 'Inactivo'} />
          </dl>

          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">Condición de pago habitual</span>
            <select
              disabled={!puedeEscribir}
              value={condicionPagoId}
              onChange={(event) => setCondicionPagoId(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50"
            >
              <option value="">Sin definir</option>
              {condicionesPago.map((condicion) => (
                <option key={condicion.id} value={condicion.id}>
                  {condicion.nombre}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">Forma de pago habitual</span>
            <select
              disabled={!puedeEscribir}
              value={formaPagoId}
              onChange={(event) => setFormaPagoId(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50"
            >
              <option value="">Sin definir</option>
              {formasPago.map((forma) => (
                <option key={forma.id} value={forma.id}>
                  {forma.nombre}
                </option>
              ))}
            </select>
          </label>

          {puedeEscribir && (
            <button
              type="submit"
              disabled={actualizarMutation.isPending}
              className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {actualizarMutation.isPending ? 'Guardando…' : 'Guardar'}
            </button>
          )}

          {actualizarMutation.isError && (
            <p className="text-sm text-red-600">No se pudo guardar el rol cliente.</p>
          )}
        </form>
      )}
    </section>
  )
}
