import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { CondicionPago, FormaPago } from '@/lib/api/catalogosComerciales'
import { ApiError } from '@/lib/api/presupuestacion'
import {
  actualizarRolProveedor,
  crearRolProveedor,
  obtenerRolProveedor,
  type ProveedorRolUpdatePayload,
  type TipoProveedor,
} from '@/lib/api/terceros'

const TIPOS_PROVEEDOR: TipoProveedor[] = [
  'laboratorio',
  'drogueria',
  'distribuidor',
  'cooperativa',
  'otro',
]

export function RolProveedorSection({
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

  const { data: rolProveedor, error, isPending } = useQuery({
    queryKey: ['terceros', terceroId, 'proveedores'],
    queryFn: () => obtenerRolProveedor(terceroId),
    retry: false,
  })

  const noTieneRol = error instanceof ApiError && error.status === 404

  const crearMutation = useMutation({
    mutationFn: () => crearRolProveedor(terceroId, {}),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'proveedores'] }),
  })

  const actualizarMutation = useMutation({
    mutationFn: (payload: ProveedorRolUpdatePayload) => actualizarRolProveedor(terceroId, payload),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'proveedores'] }),
  })

  const [tipo, setTipo] = useState<TipoProveedor>('otro')
  const [esCompetidor, setEsCompetidor] = useState(true)
  const [esProveedorCompra, setEsProveedorCompra] = useState(false)
  const [condicionPagoId, setCondicionPagoId] = useState('')
  const [formaPagoId, setFormaPagoId] = useState('')

  useEffect(() => {
    if (rolProveedor) {
      setTipo(rolProveedor.tipo)
      setEsCompetidor(rolProveedor.es_competidor)
      setEsProveedorCompra(rolProveedor.es_proveedor_compra)
      setCondicionPagoId(rolProveedor.condicion_pago_id ?? '')
      setFormaPagoId(rolProveedor.forma_pago_id ?? '')
    }
  }, [rolProveedor])

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Rol proveedor</h2>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : noTieneRol ? (
        <div>
          <p className="mb-3 text-sm text-slate-500">Este tercero no tiene rol proveedor asignado.</p>
          {puedeEscribir && (
            <button
              type="button"
              onClick={() => crearMutation.mutate()}
              disabled={crearMutation.isPending}
              className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {crearMutation.isPending ? 'Asignando…' : 'Asignar rol proveedor'}
            </button>
          )}
          {crearMutation.isError && (
            <p className="mt-2 text-sm text-red-600">No se pudo asignar el rol proveedor.</p>
          )}
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">No se pudo cargar el rol proveedor.</p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            actualizarMutation.mutate({
              tipo,
              es_competidor: esCompetidor,
              es_proveedor_compra: esProveedorCompra,
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
              onChange={(event) => setTipo(event.target.value as TipoProveedor)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50"
            >
              {TIPOS_PROVEEDOR.map((opcion) => (
                <option key={opcion} value={opcion}>
                  {opcion}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              disabled={!puedeEscribir}
              checked={esCompetidor}
              onChange={(event) => setEsCompetidor(event.target.checked)}
            />
            <span className="text-slate-600">Es competidor</span>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              disabled={!puedeEscribir}
              checked={esProveedorCompra}
              onChange={(event) => setEsProveedorCompra(event.target.checked)}
            />
            <span className="text-slate-600">Es proveedor de compra</span>
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
                onClick={() => actualizarMutation.mutate({ activo: !rolProveedor.activo })}
                className="text-sm font-medium text-accent hover:underline"
              >
                {rolProveedor.activo ? 'Desactivar rol' : 'Reactivar rol'}
              </button>
              <span
                className={rolProveedor.activo ? 'text-sm text-emerald-600' : 'text-sm text-slate-400'}
              >
                {rolProveedor.activo ? 'Activo' : 'Inactivo'}
              </span>
            </div>
          )}

          {actualizarMutation.isError && (
            <p className="text-sm text-red-600">No se pudo guardar el rol proveedor.</p>
          )}
        </form>
      )}
    </section>
  )
}
