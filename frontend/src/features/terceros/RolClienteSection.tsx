import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { CondicionPago, FormaPago } from '@/lib/api/catalogosComerciales'
import { ApiError } from '@/lib/api/presupuestacion'
import {
  actualizarRolCliente,
  crearRolCliente,
  obtenerRolCliente,
  type ClienteRolUpdatePayload,
  type TipoCliente,
} from '@/lib/api/terceros'

const TIPOS_CLIENTE: TipoCliente[] = [
  'hospital',
  'obra_social',
  'municipio',
  'provincia',
  'nacional',
  'otro',
]

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

  const crearMutation = useMutation({
    mutationFn: () => crearRolCliente(terceroId, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'clientes'] }),
  })

  const actualizarMutation = useMutation({
    mutationFn: (payload: ClienteRolUpdatePayload) => actualizarRolCliente(terceroId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'clientes'] }),
  })

  const [tipo, setTipo] = useState<TipoCliente>('otro')
  const [condicionPagoId, setCondicionPagoId] = useState('')
  const [formaPagoId, setFormaPagoId] = useState('')

  useEffect(() => {
    if (rolCliente) {
      setTipo(rolCliente.tipo)
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
        <div>
          <p className="mb-3 text-sm text-slate-500">Este tercero no tiene rol cliente asignado.</p>
          {puedeEscribir && (
            <button
              type="button"
              onClick={() => crearMutation.mutate()}
              disabled={crearMutation.isPending}
              className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {crearMutation.isPending ? 'Asignando…' : 'Asignar rol cliente'}
            </button>
          )}
          {crearMutation.isError && (
            <p className="mt-2 text-sm text-red-600">No se pudo asignar el rol cliente.</p>
          )}
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">No se pudo cargar el rol cliente.</p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            actualizarMutation.mutate({
              tipo,
              condicion_pago_id: condicionPagoId || undefined,
              forma_pago_id: formaPagoId || undefined,
            })
          }}
        >
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">Tipo</span>
            <select
              disabled={!puedeEscribir}
              value={tipo}
              onChange={(event) => setTipo(event.target.value as TipoCliente)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50"
            >
              {TIPOS_CLIENTE.map((opcion) => (
                <option key={opcion} value={opcion}>
                  {opcion}
                </option>
              ))}
            </select>
          </label>

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
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={actualizarMutation.isPending}
                className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {actualizarMutation.isPending ? 'Guardando…' : 'Guardar'}
              </button>
              <button
                type="button"
                onClick={() => actualizarMutation.mutate({ activo: !rolCliente.activo })}
                className="text-sm font-medium text-accent hover:underline"
              >
                {rolCliente.activo ? 'Desactivar rol' : 'Reactivar rol'}
              </button>
              <span className={rolCliente.activo ? 'text-sm text-emerald-600' : 'text-sm text-slate-400'}>
                {rolCliente.activo ? 'Activo' : 'Inactivo'}
              </span>
            </div>
          )}

          {actualizarMutation.isError && (
            <p className="text-sm text-red-600">No se pudo guardar el rol cliente.</p>
          )}
        </form>
      )}
    </section>
  )
}
