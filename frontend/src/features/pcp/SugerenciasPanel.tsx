import { useQuery } from '@tanstack/react-query'
import { listarSugerenciasPreciosRecientes, obtenerSugerenciaAgrupacion } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

/**
 * Panel de solo lectura (spec `pcp-ui-sugerencias`): ningún control aquí
 * llama a un endpoint de escritura de PCP, y se muestra a cualquier rol de
 * lectura sin exigir ningún rol de escritura -- por eso, a diferencia de
 * `ComparacionProveedoresTable`/`SeleccionProveedoresSection`, este
 * componente no recibe ni consulta `puedeEscribir`.
 */
export function SugerenciasPanel({ renglonId }: { renglonId: string }) {
  const agrupacionQuery = useQuery({
    queryKey: pcpQueryKeys.agrupacion(renglonId),
    queryFn: () => obtenerSugerenciaAgrupacion(renglonId),
  })
  const preciosQuery = useQuery({
    queryKey: pcpQueryKeys.preciosRecientes(renglonId),
    queryFn: () => listarSugerenciasPreciosRecientes(renglonId),
  })

  if (agrupacionQuery.isPending || preciosQuery.isPending) {
    return (
      <section role="region" aria-label="Sugerencias del renglón" className="mt-8">
        <p className="text-sm text-slate-500">Cargando sugerencias…</p>
      </section>
    )
  }

  if (agrupacionQuery.isError || preciosQuery.isError) {
    return (
      <section role="region" aria-label="Sugerencias del renglón" className="mt-8">
        <p role="alert" className="text-sm text-red-600">No se pudieron cargar las sugerencias.</p>
      </section>
    )
  }

  const agrupacion = agrupacionQuery.data ?? null
  const preciosRecientes = preciosQuery.data ?? []
  const hayDatos = agrupacion !== null || preciosRecientes.length > 0

  return (
    <section role="region" aria-label="Sugerencias del renglón" className="mt-8 space-y-4">
      <h2 className="text-lg font-semibold text-navy">Sugerencias</h2>
      {!hayDatos ? (
        <p className="text-sm text-slate-500">No hay sugerencias disponibles para este renglón.</p>
      ) : null}
      {agrupacion ? (
        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <h3 className="font-semibold text-navy">Sugerencia de agrupación por cantidad</h3>
          <p className="mt-1 text-slate-600">
            Producto <strong>{agrupacion.producto_id}</strong>
          </p>
          <p className="text-slate-600">
            Cantidad agregada: <strong>{agrupacion.cantidad_agregada}</strong>
          </p>
          <p className="text-slate-600">
            {agrupacion.renglon_ids.length} renglones agrupados en {agrupacion.pcp_ids.length} PCPs
          </p>
        </article>
      ) : null}
      {preciosRecientes.length > 0 ? (
        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <h3 className="font-semibold text-navy">Sugerencia de precio reciente</h3>
          <ul className="mt-1 space-y-3 text-slate-600">
            {preciosRecientes.map((precio) => (
              <li key={precio.precio_proveedor_id}>
                <p className="font-semibold text-navy">{precio.proveedor}</p>
                <p>
                  Vigente hasta {precio.mantenimiento_hasta} ({precio.dias_restantes} días restantes)
                </p>
                <p>
                  Cantidad {precio.cantidad_minima ?? '—'} a {precio.cantidad_maxima ?? '—'}
                </p>
                <p>Precio unitario: {precio.precio_unitario}</p>
              </li>
            ))}
          </ul>
        </article>
      ) : null}
    </section>
  )
}
