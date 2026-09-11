import { type ReactNode, useState } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/lib/api/presupuestacion'
import { obtenerResultado, actualizarSeleccion, type ProductoProveedor, type ResultadoNegociacion } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'
import { RegistrarResultadoDialog } from './RegistrarResultadoDialog'

interface Columna {
  proveedor: ProductoProveedor
  resultado: ResultadoNegociacion | null
  /** Fetch fallido con un error distinto de 404 (no confundir con "sin resultado aún"). */
  error: boolean
}

function codigoDe(proveedor: ProductoProveedor): string {
  return proveedor.codigo_proveedor ?? proveedor.proveedor_id
}

function etiquetaResultado(resultado: ResultadoNegociacion): string {
  return resultado.resultado === 'no_cotiza' ? 'No cotiza' : 'Precio obtenido'
}

/**
 * Criterios de comparación con valor uniforme entre precio_obtenido y
 * no_cotiza (siempre "—" cuando el campo no aplica). Compartidos entre la
 * fila de la tabla de escritorio y la definición de la tarjeta móvil para
 * que agregar/cambiar un criterio ocurra en un solo lugar.
 */
interface CriterioComparacion {
  clave: string
  etiqueta: string
  valor: (resultado: ResultadoNegociacion) => ReactNode
}

const CRITERIOS_COMPARACION: CriterioComparacion[] = [
  { clave: 'precio_unitario', etiqueta: 'Precio unitario', valor: (resultado) => resultado.precio_unitario ?? '—' },
  {
    clave: 'cantidad',
    etiqueta: 'Cantidad mín./máx.',
    valor: (resultado) => `${resultado.cantidad_minima ?? '—'} / ${resultado.cantidad_maxima ?? '—'}`,
  },
  { clave: 'mantenimiento', etiqueta: 'Mantenimiento hasta', valor: (resultado) => resultado.mantenimiento_hasta ?? '—' },
  {
    clave: 'condicion_pago',
    etiqueta: 'Condición/forma de pago',
    valor: (resultado) => `${resultado.condicion_pago_id ?? '—'} / ${resultado.forma_pago_id ?? '—'}`,
  },
]

async function obtenerResultadoOSinDato(
  pcpId: string,
  renglonId: string,
  proveedorId: string,
): Promise<ResultadoNegociacion | null> {
  try {
    return await obtenerResultado(pcpId, renglonId, proveedorId)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function ComparacionProveedoresTable({
  pcpId,
  renglonId,
  proveedores,
  puedeEscribir,
}: {
  pcpId: string
  renglonId: string
  proveedores: ProductoProveedor[]
  puedeEscribir: boolean
}) {
  const queryClient = useQueryClient()
  const [proveedorPendiente, setProveedorPendiente] = useState<string | null>(null)
  const [proveedorConError, setProveedorConError] = useState<string | null>(null)

  const consultas = useQueries({
    queries: proveedores.map((proveedor) => ({
      queryKey: pcpQueryKeys.resultado(pcpId, renglonId, proveedor.proveedor_id),
      queryFn: () => obtenerResultadoOSinDato(pcpId, renglonId, proveedor.proveedor_id),
    })),
  })

  if (proveedores.length === 0) {
    return <p className="mt-8 text-sm text-slate-500">No hay proveedores catalogados para este renglón.</p>
  }

  if (consultas.some((consulta) => consulta.isPending)) {
    return <p className="mt-8 text-sm text-slate-500">Cargando comparación…</p>
  }

  const columnas: Columna[] = proveedores.map((proveedor, index) => ({
    proveedor,
    resultado: consultas[index].data ?? null,
    error: consultas[index].isError,
  }))

  async function alternarSeleccion(columna: Columna) {
    if (!columna.resultado) return
    const proveedorId = columna.proveedor.proveedor_id
    setProveedorPendiente(proveedorId)
    setProveedorConError(null)
    try {
      const actualizado = await actualizarSeleccion(pcpId, renglonId, proveedorId, !columna.resultado.seleccionado)
      queryClient.setQueryData<ResultadoNegociacion | null>(
        pcpQueryKeys.resultado(pcpId, renglonId, proveedorId),
        (actual) => (actual ? { ...actual, seleccionado: actualizado.seleccionado } : actual),
      )
      queryClient.invalidateQueries({ queryKey: pcpQueryKeys.seleccion(pcpId) })
    } catch {
      setProveedorConError(proveedorId)
    } finally {
      setProveedorPendiente(null)
    }
  }

  return (
    <div className="mt-8">
      {/* Escritorio: una columna por proveedor, una fila por criterio. */}
      <table aria-label="Comparación de proveedores" className="hidden w-full border-collapse text-sm md:table">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th scope="col" />
            {columnas.map(({ proveedor, resultado }) => (
              <th key={proveedor.id} scope="col" className={`p-2 font-semibold text-navy ${resultado?.seleccionado ? 'bg-emerald-50' : ''}`}>
                {codigoDe(proveedor)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-slate-100">
            <th scope="row" className="p-2 text-left font-medium text-slate-600">Resultado</th>
            {columnas.map(({ proveedor, resultado, error }) => (
              <td
                key={proveedor.id}
                className={`p-2 ${resultado?.seleccionado ? 'bg-emerald-50' : ''} ${error ? 'text-red-600' : ''}`}
                title={resultado ? etiquetaResultado(resultado) : error ? 'Error al cargar el resultado' : 'Sin resultado aún'}
              >
                {resultado ? (resultado.resultado === 'no_cotiza' ? '✕' : '✓') : error ? '⚠' : '—'}
              </td>
            ))}
          </tr>
          {CRITERIOS_COMPARACION.map((criterio) => (
            <tr key={criterio.clave} className="border-b border-slate-100">
              <th scope="row" className="p-2 text-left font-medium text-slate-600">{criterio.etiqueta}</th>
              {columnas.map(({ proveedor, resultado }) => (
                <td key={proveedor.id} className="p-2">{resultado ? criterio.valor(resultado) : '—'}</td>
              ))}
            </tr>
          ))}
          <tr className="border-b border-slate-100">
            <th scope="row" className="p-2 text-left font-medium text-slate-600">Motivo</th>
            {columnas.map(({ proveedor, resultado }) => (
              <td key={proveedor.id} className="p-2" title={resultado?.motivo ?? undefined}>{resultado?.motivo ? '…' : '—'}</td>
            ))}
          </tr>
          {puedeEscribir ? (
            <tr>
              <th scope="row" className="p-2 text-left font-medium text-slate-600">Acción</th>
              {columnas.map((columna) => (
                <td key={columna.proveedor.id} className="space-x-2 p-2">
                  <RegistrarResultadoDialog pcpId={pcpId} renglonId={renglonId} proveedor={columna.proveedor} />
                  {columna.resultado ? (
                    <button
                      type="button"
                      disabled={proveedorPendiente === columna.proveedor.proveedor_id}
                      onClick={() => alternarSeleccion(columna)}
                      className="min-h-9 rounded-md border border-slate-300 px-3 text-sm font-medium text-navy disabled:opacity-50"
                    >
                      {columna.resultado.seleccionado
                        ? `Quitar selección de ${codigoDe(columna.proveedor)}`
                        : `Seleccionar proveedor ${codigoDe(columna.proveedor)}`}
                    </button>
                  ) : null}
                  {proveedorConError === columna.proveedor.proveedor_id ? (
                    <p role="alert" className="mt-1 text-xs text-red-600">No se pudo actualizar la selección.</p>
                  ) : null}
                </td>
              ))}
            </tr>
          ) : null}
        </tbody>
      </table>

      {/* Móvil: una tarjeta por proveedor, apiladas debajo del breakpoint md. */}
      <ul aria-label="Comparación de proveedores en tarjetas" className="space-y-4 md:hidden">
        {columnas.map(({ proveedor, resultado, error }) => (
          <li
            key={proveedor.id}
            className={`rounded-lg border border-slate-200 p-4 text-sm ${resultado?.seleccionado ? 'bg-emerald-50' : 'bg-white'}`}
          >
            <p className="font-semibold text-navy">{codigoDe(proveedor)}</p>
            {resultado ? (
              <>
                <p className="mt-1">{etiquetaResultado(resultado)}</p>
                {resultado.resultado === 'no_cotiza' ? (
                  resultado.motivo ? <p className="mt-1 text-slate-600">{resultado.motivo}</p> : null
                ) : (
                  <dl className="mt-1 space-y-0.5 text-slate-600">
                    {CRITERIOS_COMPARACION.map((criterio) => (
                      <div key={criterio.clave}>
                        <dt className="inline font-medium">{criterio.etiqueta}: </dt>
                        <dd className="inline">{criterio.valor(resultado)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {resultado.seleccionado ? <p className="mt-2 font-semibold text-emerald-700">Seleccionado</p> : null}
              </>
            ) : error ? (
              <p className="mt-1 text-red-600" role="alert">Error al cargar el resultado</p>
            ) : (
              <p className="mt-1 text-slate-500">Sin resultado aún</p>
            )}
            {puedeEscribir ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <RegistrarResultadoDialog pcpId={pcpId} renglonId={renglonId} proveedor={proveedor} />
                {resultado ? (
                  <button
                    type="button"
                    disabled={proveedorPendiente === proveedor.proveedor_id}
                    onClick={() => alternarSeleccion({ proveedor, resultado, error: false })}
                    className="min-h-9 rounded-md border border-slate-300 px-3 text-sm font-medium text-navy disabled:opacity-50"
                  >
                    {resultado.seleccionado ? 'Quitar selección' : 'Seleccionar proveedor'}
                  </button>
                ) : null}
                {proveedorConError === proveedor.proveedor_id ? (
                  <p role="alert" className="mt-1 w-full text-xs text-red-600">No se pudo actualizar la selección.</p>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
