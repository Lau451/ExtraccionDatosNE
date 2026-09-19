import { Link } from '@tanstack/react-router'
import type { ExtraccionResumen } from '@/lib/api/extracciones'

const ETIQUETA_TIPO: Record<string, string> = {
  licitacion: 'Licitación',
  cotizacion: 'Directa',
  comparativa: 'Comparativa',
  orden_compra: 'Orden de compra',
}

interface PendientesTableProps {
  extracciones: ExtraccionResumen[]
  seleccionados?: Set<string>
  onAlternarSeleccion?: (id: string) => void
  // D13 -- extraction_id -> grupo_id, rastreado por ValidarExtraccionListado
  // en memoria (GET /extracciones no expone grupo_id, fuera de este alcance).
  gruposLocales?: Record<string, string>
}

export function PendientesTable({
  extracciones,
  seleccionados,
  onAlternarSeleccion,
  gruposLocales = {},
}: PendientesTableProps) {
  if (extracciones.length === 0) {
    return <p className="text-sm text-slate-500">No hay extracciones para mostrar.</p>
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="py-2 font-medium" />
          <th className="py-2 font-medium">Documento</th>
          <th className="py-2 font-medium">Tipo</th>
          <th className="py-2 font-medium">Filas</th>
          <th className="py-2 font-medium">Proceso comercial</th>
          <th className="py-2 font-medium">Cargado</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {extracciones.map((extraccion) => {
          // D13 -- solo orden_compra sin validar se puede tildar para
          // agrupar/desagrupar (este listado ya filtra validado=false).
          const esAgrupable = extraccion.document_type === 'orden_compra'
          const grupoId = gruposLocales[extraccion.id]

          return (
            <tr key={extraccion.id} className="border-b border-slate-100">
              <td className="py-2">
                {esAgrupable && onAlternarSeleccion && (
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
              <td className="py-2 text-slate-600">
                {ETIQUETA_TIPO[extraccion.document_type] ?? extraccion.document_type}
              </td>
              <td className="py-2 text-slate-600">{extraccion.row_count}</td>
              <td className="py-2 text-slate-600">{extraccion.proceso_comercial_nombre ?? '—'}</td>
              <td className="py-2 text-slate-500">
                {new Date(extraccion.created_at).toLocaleDateString('es-AR')}
              </td>
              <td className="py-2 text-right">
                <Link
                  to="/validar-extraccion/$extractionId"
                  params={{ extractionId: extraccion.id }}
                  search={{ rowCount: extraccion.row_count }}
                  className="text-sm font-medium text-accent hover:underline"
                >
                  Revisar
                </Link>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
