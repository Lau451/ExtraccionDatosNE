import { Link } from '@tanstack/react-router'
import type { ExtraccionResumen } from '@/lib/api/extracciones'

interface ValidadasTableProps {
  extracciones: ExtraccionResumen[]
}

/** D11 (`orden-compra-matching-presupuesto`) -- sección "Órdenes de compra
 * validadas" del listado: re-entrada a la pantalla de matching para una OC
 * ya confirmada, sin depender de la navegación automática (D10) ni de haber
 * guardado el permalink. `orden_compra_id` puede venir `null` para un
 * miembro no-ancla de un grupo multi-archivo (D13 del cambio padre) --
 * mismo criterio que `proceso_comercial_nombre` en PendientesTable: la fila
 * se muestra igual, sin acción rota, en vez de ocultarse. */
export function ValidadasTable({ extracciones }: ValidadasTableProps) {
  if (extracciones.length === 0) {
    return <p className="text-sm text-slate-500">No hay órdenes de compra validadas.</p>
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="py-2 font-medium">Documento</th>
          <th className="py-2 font-medium">Filas</th>
          <th className="py-2 font-medium">Proceso comercial</th>
          <th className="py-2 font-medium">Cargado</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {extracciones.map((extraccion) => (
          <tr key={extraccion.id} className="border-b border-slate-100">
            <td className="max-w-xs truncate py-2 text-slate-900">{extraccion.source_filename}</td>
            <td className="py-2 text-slate-600">{extraccion.row_count}</td>
            <td className="py-2 text-slate-600">{extraccion.proceso_comercial_nombre ?? '—'}</td>
            <td className="py-2 text-slate-500">
              {new Date(extraccion.created_at).toLocaleDateString('es-AR')}
            </td>
            <td className="py-2 text-right">
              {extraccion.orden_compra_id ? (
                <Link
                  to="/ordenes-compra/$ordenCompraId/matching"
                  params={{ ordenCompraId: extraccion.orden_compra_id }}
                  className="text-sm font-medium text-accent hover:underline"
                >
                  Matching
                </Link>
              ) : (
                <span className="text-xs text-slate-400">—</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
