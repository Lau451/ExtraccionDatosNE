import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import {
  ajustarStock,
  crearCosto,
  listarCostos,
  listarStock,
  obtenerProducto,
} from '@/lib/api/productos'
import { COSTOS_READ_ROLES, PRODUCTOS_WRITE_ROLES, puedeRol } from './roles'

export function ProductoDetalle({ productoId }: { productoId: string }) {
  const { perfil } = useAuth()
  const puedeEscribir = puedeRol(perfil?.rol, PRODUCTOS_WRITE_ROLES)
  const puedeVerCostos = puedeRol(perfil?.rol, COSTOS_READ_ROLES)

  const { data: producto, isPending } = useQuery({
    queryKey: ['productos', productoId],
    queryFn: () => obtenerProducto(productoId),
  })

  if (isPending) {
    return <p className="p-8 text-sm text-slate-500">Cargando…</p>
  }

  return (
    <div className="p-8">
      <Link to="/productos" className="mb-4 inline-block text-sm text-accent hover:underline">
        ← Volver a productos
      </Link>

      <h1 className="mb-1 text-xl font-semibold text-navy">{producto?.nombre}</h1>
      <p className="mb-6 text-sm text-slate-500">Código interno: {producto?.codigo_interno}</p>

      <div className="grid gap-8 md:grid-cols-2">
        {puedeVerCostos ? (
          <CostosSection productoId={productoId} puedeEscribir={puedeEscribir} />
        ) : (
          <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Historial de costos</h2>
            <p className="text-sm text-slate-500">No tenés permiso para ver los costos.</p>
          </section>
        )}
        <StockSection productoId={productoId} puedeEscribir={puedeEscribir} />
      </div>
    </div>
  )
}

function CostosSection({ productoId, puedeEscribir }: { productoId: string; puedeEscribir: boolean }) {
  const queryClient = useQueryClient()
  const [costoUnitario, setCostoUnitario] = useState('')
  const [fechaDesde, setFechaDesde] = useState('')

  const { data: costos, isPending } = useQuery({
    queryKey: ['productos', productoId, 'costos'],
    queryFn: () => listarCostos(productoId),
  })

  const crearMutation = useMutation({
    mutationFn: () => crearCosto(productoId, { costo_unitario: Number(costoUnitario), fecha_desde: fechaDesde }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['productos', productoId, 'costos'] })
      setCostoUnitario('')
      setFechaDesde('')
    },
  })

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Historial de costos</h2>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Desde</th>
              <th className="py-2 font-medium">Hasta</th>
              <th className="py-2 font-medium">Costo unitario</th>
              <th className="py-2 font-medium">Origen</th>
            </tr>
          </thead>
          <tbody>
            {costos?.map((costo) => (
              <tr key={costo.id} className="border-b border-slate-100">
                <td className="py-2">{costo.fecha_desde}</td>
                <td className="py-2 text-slate-500">{costo.fecha_hasta ?? '—'}</td>
                <td className="py-2">{costo.costo_unitario}</td>
                <td className="py-2 text-slate-500">{costo.origen}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {puedeEscribir && (
        <form
          className="mt-4 flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            crearMutation.mutate()
          }}
        >
          <label className="text-sm">
            <span className="mb-1 block text-slate-600">Costo unitario</span>
            <input
              required
              type="number"
              step="0.01"
              min="0"
              value={costoUnitario}
              onChange={(event) => setCostoUnitario(event.target.value)}
              className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-600">Desde</span>
            <input
              required
              type="date"
              value={fechaDesde}
              onChange={(event) => setFechaDesde(event.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={crearMutation.isPending}
            className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {crearMutation.isPending ? 'Cargando…' : 'Cargar costo'}
          </button>
        </form>
      )}

      {crearMutation.isError && (
        <p className="mt-2 text-sm text-red-600">No se pudo cargar el costo.</p>
      )}
    </section>
  )
}

function StockSection({ productoId, puedeEscribir }: { productoId: string; puedeEscribir: boolean }) {
  const queryClient = useQueryClient()

  const { data: stock, isPending } = useQuery({
    queryKey: ['productos', productoId, 'stock'],
    queryFn: () => listarStock(productoId),
  })

  const ajustarMutation = useMutation({
    mutationFn: ({ deposito, cantidad_disponible }: { deposito: string; cantidad_disponible: number }) =>
      ajustarStock(productoId, { deposito: deposito || undefined, cantidad_disponible }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['productos', productoId, 'stock'] }),
  })

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Stock por depósito</h2>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Depósito</th>
              <th className="py-2 font-medium">Disponible</th>
              <th className="py-2 font-medium">Comprometida</th>
              {puedeEscribir && <th className="py-2 font-medium" />}
            </tr>
          </thead>
          <tbody>
            {stock?.map((fila) => (
              <FilaStock
                key={fila.id}
                deposito={fila.deposito ?? ''}
                cantidadDisponible={fila.cantidad_disponible}
                cantidadComprometida={fila.cantidad_comprometida}
                puedeEscribir={puedeEscribir}
                onAjustar={(cantidad) =>
                  ajustarMutation.mutate({ deposito: fila.deposito ?? '', cantidad_disponible: cantidad })
                }
              />
            ))}
          </tbody>
        </table>
      )}

      {ajustarMutation.isError && (
        <p className="mt-2 text-sm text-red-600">No se pudo ajustar el stock.</p>
      )}
    </section>
  )
}

function FilaStock({
  deposito,
  cantidadDisponible,
  cantidadComprometida,
  puedeEscribir,
  onAjustar,
}: {
  deposito: string
  cantidadDisponible: number
  cantidadComprometida: number
  puedeEscribir: boolean
  onAjustar: (cantidad: number) => void
}) {
  const [valor, setValor] = useState(String(cantidadDisponible))

  return (
    <tr className="border-b border-slate-100">
      <td className="py-2">{deposito || '—'}</td>
      <td className="py-2">
        {puedeEscribir ? (
          <input
            type="number"
            step="1"
            value={valor}
            onChange={(event) => setValor(event.target.value)}
            className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
        ) : (
          cantidadDisponible
        )}
      </td>
      <td className="py-2 text-slate-500">{cantidadComprometida}</td>
      {puedeEscribir && (
        <td className="py-2 text-right">
          <button
            type="button"
            onClick={() => onAjustar(Number(valor))}
            className="text-sm font-medium text-accent hover:underline"
          >
            Ajustar
          </button>
        </td>
      )}
    </tr>
  )
}
