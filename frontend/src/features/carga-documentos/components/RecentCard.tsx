import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import clsx from 'clsx'
import { listarDocumentosRecientes, type DocumentoReciente, type EstadoExtraccion } from '@/lib/api/extraccion'

const RECIENTES_KEY = ['documentos-recientes']

// El texto es siempre el indicador principal (no solo el color, WCAG 1.4.1) --
// el color de cada badge es un refuerzo visual, nunca la única señal.
const STATUS_META: Record<EstadoExtraccion, { label: string; badgeClass: string; pulso?: boolean }> = {
  processing: { label: 'Procesando', badgeClass: 'bg-amber-100 text-amber-700', pulso: true },
  completed: { label: 'Listo para validar', badgeClass: 'bg-emerald-100 text-emerald-700' },
  partial: { label: 'Listo para validar', badgeClass: 'bg-emerald-100 text-emerald-700' },
  failed: { label: 'Error', badgeClass: 'bg-red-100 text-red-700' },
}

// Validación solo acepta completed/partial (carga-asincrona T1) -- si el
// listado no trae `validado`, se ofrece igual "Validar" para cualquiera de
// los dos: la pantalla de validación ya maneja una extracción ya validada.
const ESTADOS_VALIDABLES: EstadoExtraccion[] = ['completed', 'partial']

function haySinTerminar(documentos: DocumentoReciente[]): boolean {
  return documentos.some((doc) => doc.status === 'processing')
}

function resumenEstado(documentos: DocumentoReciente[]): string {
  const procesando = documentos.filter((doc) => doc.status === 'processing').length
  if (procesando === 0) return 'Sin documentos procesándose.'
  return `${procesando} documento${procesando === 1 ? '' : 's'} procesándose.`
}

export function RecentCard() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: RECIENTES_KEY,
    queryFn: () => listarDocumentosRecientes(),
    // El robot corre en background (carga-asincrona T1) -- mientras haya algo
    // 'processing' se pollea cada ~3s para reflejar la transición a
    // completed/failed sin que el usuario tenga que refrescar. Se apaga solo
    // apenas no queda nada pendiente, en vez de pollear para siempre.
    refetchInterval: (query) => (haySinTerminar(query.state.data?.documentos ?? []) ? 3000 : false),
  })

  // T3 (revisión de T2): la región aria-live y `refetchInterval` deben leer
  // la MISMA lista -- antes el resumen contaba solo sobre el top-3 visible
  // (`documentos`) mientras el polling miraba la lista completa; con más de
  // 3 documentos recientes, un "processing" fuera del top-3 se pisaba sin
  // que el lector de pantalla se enterara.
  const todosLosDocumentos = data?.documentos ?? []
  const documentos = todosLosDocumentos.slice(0, 3)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-sm font-semibold text-slate-900">Cargas recientes</h2>

      {/* Región viva para lectores de pantalla -- anuncia cuántos documentos
       * siguen procesándose sin depender de que el usuario mire el color de
       * cada badge (WCAG 4.1.3). Visualmente oculta (sr-only). */}
      <div aria-live="polite" role="status" className="sr-only">
        {todosLosDocumentos.length > 0 ? resumenEstado(todosLosDocumentos) : ''}
      </div>

      {isLoading && <p className="text-sm text-slate-500">Cargando…</p>}

      {!isLoading && documentos.length === 0 && (
        <p className="text-sm text-slate-500">Todavía no se cargaron documentos.</p>
      )}

      <ul className="space-y-2">
        {documentos.map((doc) => {
          const meta = STATUS_META[doc.status] ?? {
            label: doc.status,
            badgeClass: 'bg-slate-100 text-slate-600',
          }
          const puedeValidar = ESTADOS_VALIDABLES.includes(doc.status)

          return (
            <li key={doc.id} className="space-y-1.5 border-b border-slate-100 pb-2 last:border-0 last:pb-0">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{doc.source_filename}</p>
                  <p className="text-xs text-slate-500">{doc.proceso_comercial?.nombre ?? 'Sin vincular'}</p>
                </div>
                <span
                  className={clsx(
                    'flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
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
              </div>

              {doc.status === 'failed' && (
                <p className="text-xs text-red-600">
                  {doc.error_msg ?? 'No se pudo procesar el documento.'} Podés volver a subirlo.
                </p>
              )}

              {puedeValidar && (
                <button
                  type="button"
                  onClick={() =>
                    navigate({
                      to: '/validar-extraccion/$extractionId',
                      params: { extractionId: doc.id },
                      search: { rowCount: doc.row_count },
                    })
                  }
                  className="cursor-pointer rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1"
                >
                  Validar
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
