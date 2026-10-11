import { presupuestacionFetch } from './presupuestacion'

/** Espejo literal de `oc_export/models.py::ResultadoExportacion`. */
export interface ResultadoExportacion {
  archivo: string
  exportado_at: string
  exportado_por: string
  filas: number
}

/** POST /ordenes-compra/{id}/exportar-progress: genera el CSV para Progress y
 * marca la OC como exportada (el plan deja de poder modificarse). Errores
 * (`ApiError`, `detail` del backend tal cual): 422 todas las precondiciones
 * fallidas juntas, separadas por "; "; 409 ya exportada o plan modificado
 * durante la exportación; 503 integración no configurada
 * (`PROGRESS_DOCS_DIR`); 403 rol sin permiso (`compras`). */
export async function exportarAProgress(ordenCompraId: string): Promise<ResultadoExportacion> {
  return presupuestacionFetch<ResultadoExportacion>(`/ordenes-compra/${ordenCompraId}/exportar-progress`, {
    method: 'POST',
  })
}
