import { Link } from '@tanstack/react-router'
import clsx from 'clsx'
import type { DocumentType, ExtraccionResumen } from '@/lib/api/extracciones'
import { ESTADO_META, esEstadoValidable, estadoDerivadoDe } from '../estadoExtraccion'
import { grupoIdDe } from '../ValidarExtraccionListado'

interface ExtraccionesTableProps {
  extracciones: ExtraccionResumen[]
  // T2 -- Agrupar/Desagrupar y los checkboxes de selección solo tienen
  // sentido en la tab Orden de compra (decisión de usuario, 2026-09-26); el
  // resto de las tabs renderiza la misma tabla sin esas columnas activas.
  tipoActivo: DocumentType
  seleccionados?: Set<string>
  onAlternarSeleccion?: (id: string) => void
  // D13/7.13 -- override OPTIMISTA post-agrupar/desagrupar de esta sesión (ver
  // grupoIdDe); cuando no hay override se usa extraccion.grupo_id, el dato
  // real que ya devuelve GET /extracciones.
  gruposLocales?: Record<string, string | null>
}

/** T2 -- celda de acción por fila: "Revisar" para procesado/procesado con
 * advertencias (cualquier tipo); "Matching" solo para una OC ya validada con
 * `orden_compra_id` resuelto (D11); sin acción para procesando/error, y para
 * una fila validada sin OC resuelta o que no es orden_compra (informativa). */
function AccionCelda({ extraccion }: { extraccion: ExtraccionResumen }) {
  const estado = estadoDerivadoDe(extraccion)

  if (esEstadoValidable(estado)) {
    return (
      <Link
        to="/validar-extraccion/$extractionId"
        params={{ extractionId: extraccion.id }}
        search={{ rowCount: extraccion.row_count }}
        className="text-sm font-medium text-accent hover:underline"
      >
        Revisar
      </Link>
    )
  }

  if (estado === 'validada' && extraccion.document_type === 'orden_compra' && extraccion.orden_compra_id) {
    return (
      <Link
        to="/ordenes-compra/$ordenCompraId/matching"
        params={{ ordenCompraId: extraccion.orden_compra_id }}
        className="text-sm font-medium text-accent hover:underline"
      >
        Matching
      </Link>
    )
  }

  return <span className="text-xs text-slate-400">—</span>
}

export function ExtraccionesTable({
  extracciones,
  tipoActivo,
  seleccionados,
  onAlternarSeleccion,
  gruposLocales = {},
}: ExtraccionesTableProps) {
  if (extracciones.length === 0) {
    return <p className="text-sm text-slate-500">No hay extracciones para mostrar.</p>
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="py-2 font-medium" />
          <th className="py-2 font-medium">Documento</th>
          <th className="py-2 font-medium">Estado</th>
          <th className="py-2 font-medium">Filas</th>
          <th className="py-2 font-medium">Proceso comercial</th>
          <th className="py-2 font-medium">Cargado por</th>
          <th className="py-2 font-medium">Cargado</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {extracciones.map((extraccion) => {
          const estado = estadoDerivadoDe(extraccion)
          const meta = ESTADO_META[estado]
          // D13 -- solo orden_compra en estado validable (no procesando, no
          // error, no ya validada) se puede tildar para agrupar/desagrupar.
          const esSeleccionable =
            tipoActivo === 'orden_compra' && extraccion.document_type === 'orden_compra' && esEstadoValidable(estado)
          const grupoId = grupoIdDe(extraccion, gruposLocales)

          return (
            <tr key={extraccion.id} className="border-b border-slate-100">
              <td className="py-2">
                {esSeleccionable && onAlternarSeleccion && (
                  <input
                    type="checkbox"
                    aria-label={`Seleccionar ${extraccion.source_filename}`}
                    checked={seleccionados?.has(extraccion.id) ?? false}
                    onChange={() => onAlternarSeleccion(extraccion.id)}
                  />
                )}
              </td>
              <td className="max-w-xs truncate py-2 text-slate-900">
                {extraccion.source_filename}
                {grupoId && (
                  <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                    Grupo
                  </span>
                )}
              </td>
              <td className="py-2">
                <span
                  className={clsx(
                    'flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
                    meta.badgeClass,
                  )}
                >
                  {meta.pulso && (
                    <span
                      aria-hidden="true"
                      className="h-1.5 w-1.5 rounded-full bg-amber-500 motion-safe:animate-pulse"
                    />
                  )}
                  {meta.label}
                </span>
                {estado === 'error' && (
                  <p className="mt-1 text-xs text-red-600">
                    {extraccion.error_msg ?? 'No se pudo procesar el documento.'}
                  </p>
                )}
              </td>
              <td className="py-2 text-slate-600">{extraccion.row_count}</td>
              <td className="py-2 text-slate-600">{extraccion.proceso_comercial_nombre ?? '—'}</td>
              <td className="py-2 text-slate-600">{extraccion.subido_por_nombre ?? '—'}</td>
              <td className="py-2 text-slate-500">
                {new Date(extraccion.created_at).toLocaleDateString('es-AR')}
              </td>
              <td className="py-2 text-right">
                <AccionCelda extraccion={extraccion} />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
