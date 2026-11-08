import { Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import {
  asignarCaracteristicaProducto,
  listarCaracteristicas,
  listarCaracteristicasProducto,
  listarCategorias,
  listarCostos,
  listarEnvases,
  listarMarcas,
  listarStock,
  obtenerProducto,
  quitarCaracteristicaProducto,
  type Producto,
} from '@/lib/api/productos'

export function ProductoDetalle({ productoId }: { productoId: string }) {
  const { puede } = useAuth()
  const puedeEscribir = puede('productos.escribir')
  const puedeVerCostos = puede('productos.costos.leer')

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
      <p className="mb-1 text-sm text-slate-500">Código interno: {producto?.codigo_interno}</p>
      <p className="mb-6 text-sm text-slate-500">Los productos se dan de alta y se editan en Progress.</p>

      {producto && <DatosProducto producto={producto} />}

      <div className="mt-8 grid gap-8 md:grid-cols-2">
        {puedeVerCostos ? (
          <CostosSection productoId={productoId} />
        ) : (
          <section>
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Historial de costos</h2>
            <p className="text-sm text-slate-500">No tenés permiso para ver los costos.</p>
          </section>
        )}
        <StockSection productoId={productoId} />
        <CaracteristicasSection productoId={productoId} puedeEscribir={puedeEscribir} />
      </div>
    </div>
  )
}

/** Campos de Progress: se muestran, no se editan (los pisa la importación). */
function DatosProducto({ producto }: { producto: Producto }) {
  const { data: categorias } = useQuery({ queryKey: ['categorias'], queryFn: listarCategorias })
  const { data: marcas } = useQuery({ queryKey: ['marcas'], queryFn: listarMarcas })
  const { data: envases } = useQuery({ queryKey: ['envases'], queryFn: listarEnvases })

  const campos: [string, string | number | null][] = [
    ['Categoría', categorias?.find((c) => c.id === producto.categoria_id)?.nombre ?? null],
    ['Clasificación', producto.clasificacion],
    ['Droga', producto.droga],
    ['Presentación', producto.presentacion],
    ['Forma farmacéutica', producto.forma_farmaceutica],
    ['Marca', marcas?.find((m) => m.id === producto.marca_id)?.nombre ?? null],
    ['Envase', envases?.find((e) => e.id === producto.envase_id)?.nombre ?? null],
    ['Alícuota IVA (%)', producto.alicuota_iva],
    ['Código ANMAT', producto.codigo_anmat],
    ['Estado', producto.activo ? 'Activo' : 'Inactivo'],
  ]

  return (
    <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
      {campos.map(([etiqueta, valor]) => (
        <div key={etiqueta}>
          <dt className="text-slate-500">{etiqueta}</dt>
          <dd className="text-slate-900">{valor ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

function CostosSection({ productoId }: { productoId: string }) {
  const { data: costos, isPending } = useQuery({
    queryKey: ['productos', productoId, 'costos'],
    queryFn: () => listarCostos(productoId),
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
    </section>
  )
}

function StockSection({ productoId }: { productoId: string }) {
  const { data: stock, isPending } = useQuery({
    queryKey: ['productos', productoId, 'stock'],
    queryFn: () => listarStock(productoId),
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
            </tr>
          </thead>
          <tbody>
            {stock?.map((fila) => (
              <tr key={fila.id} className="border-b border-slate-100">
                <td className="py-2">{fila.deposito || '—'}</td>
                <td className="py-2">{fila.cantidad_disponible}</td>
                <td className="py-2 text-slate-500">{fila.cantidad_comprometida}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

/** Las características no vienen de Progress: es lo único del producto que
 * se escribe en la app. Cada checkbox asigna o quita en el momento. */
function CaracteristicasSection({ productoId, puedeEscribir }: { productoId: string; puedeEscribir: boolean }) {
  const queryClient = useQueryClient()
  const clave = ['productos', productoId, 'caracteristicas']

  const { data: caracteristicas } = useQuery({
    queryKey: ['caracteristicas'],
    queryFn: listarCaracteristicas,
  })
  const { data: asignadas } = useQuery({
    queryKey: clave,
    queryFn: () => listarCaracteristicasProducto(productoId),
  })
  const idsAsignados = new Set(asignadas?.map((c) => c.caracteristica_id) ?? [])

  const mutation = useMutation({
    mutationFn: ({ caracteristicaId, asignar }: { caracteristicaId: string; asignar: boolean }) =>
      asignar
        ? asignarCaracteristicaProducto(productoId, caracteristicaId).then(() => undefined)
        : quitarCaracteristicaProducto(productoId, caracteristicaId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clave }),
  })

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Características</h2>
      <div className="flex flex-wrap gap-3 text-sm">
        {(caracteristicas ?? []).map((caracteristica) => (
          <label key={caracteristica.id} className="flex items-center gap-1.5 text-slate-700">
            <input
              type="checkbox"
              disabled={!puedeEscribir || mutation.isPending}
              checked={idsAsignados.has(caracteristica.id)}
              onChange={(event) =>
                mutation.mutate({ caracteristicaId: caracteristica.id, asignar: event.target.checked })
              }
            />
            {caracteristica.nombre}
          </label>
        ))}
      </div>

      {mutation.isError && (
        <p className="mt-2 text-sm text-red-600">No se pudo guardar la característica.</p>
      )}
    </section>
  )
}
