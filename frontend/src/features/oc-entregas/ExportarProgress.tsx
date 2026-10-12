import { useState } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import type { ExportacionOut } from '@/lib/api/ocEntregas'
import type { ResultadoExportacion } from '@/lib/api/ocExport'
import { ApiError } from '@/lib/api/presupuestacion'
import { fechaLegible } from '@/lib/fechas'

// El 422 del backend junta todas las precondiciones en un solo `detail`:
// "<prefijo>: <error 1>; <error 2>" (oc_export/service.py::exportar_orden_compra).
const SEPARADOR_PREFIJO = ': '
const SEPARADOR_ERRORES = '; '

interface BannerProps {
  exportacion: ExportacionOut
}

/** Aviso persistente de una OC ya exportada (design D11). */
export function BannerExportada({ exportacion }: BannerProps) {
  return (
    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
      <p>
        Exportada a Progress el {fechaLegible(exportacion.exportado_at)}
        {exportacion.exportado_por_nombre ? ` por ${exportacion.exportado_por_nombre}` : ''}. El plan ya no
        puede modificarse.
      </p>
      <p>Archivo: {exportacion.archivo_exportado}</p>
    </div>
  )
}

function ErrorExportacion({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.status === 422 && typeof error.message === 'string') {
    const indice = error.message.indexOf(SEPARADOR_PREFIJO)
    const encabezado = indice >= 0 ? error.message.slice(0, indice) : error.message
    const detalle = indice >= 0 ? error.message.slice(indice + SEPARADOR_PREFIJO.length) : ''
    return (
      <div role="alert" className="text-sm text-red-600">
        <p>{encabezado}:</p>
        <ul className="list-disc pl-5">
          {detalle
            .split(SEPARADOR_ERRORES)
            .filter(Boolean)
            .map((motivo) => (
              <li key={motivo}>{motivo}</li>
            ))}
        </ul>
      </div>
    )
  }
  if (error instanceof ApiError && error.status === 503) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Exportación no disponible: {error.message}
      </p>
    )
  }
  return (
    <p role="alert" className="text-sm text-red-600">
      {error instanceof Error ? error.message : 'No se pudo exportar la orden de compra.'}
    </p>
  )
}

interface Props {
  /** Plan guardado, sin cambios pendientes y sin exportar. */
  habilitado: boolean
  motivoDeshabilitado: string | null
  isPending: boolean
  error: unknown
  resultado: ResultadoExportacion | null
  onExportar: () => void
}

/** Botón "Exportar a Progress" con confirmación, errores del backend y
 * resultado (design D11). Presentacional: la mutación vive en el container
 * para sobrevivir al cambio a la vista de solo lectura. */
export function ExportarProgress({ habilitado, motivoDeshabilitado, isPending, error, resultado, onExportar }: Props) {
  const [confirmando, setConfirmando] = useState(false)

  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={!habilitado || isPending}
        onClick={() => setConfirmando(true)}
        className="rounded-md border border-navy px-4 py-2 text-sm font-medium text-navy disabled:opacity-50"
      >
        Exportar a Progress
      </button>
      {!habilitado && motivoDeshabilitado && <p className="text-xs text-slate-500">{motivoDeshabilitado}</p>}
      {error != null && <ErrorExportacion error={error} />}
      {resultado && (
        <p className="text-sm text-emerald-800">
          Exportación generada: {resultado.archivo} ({resultado.filas} filas).
        </p>
      )}
      <ConfirmDialog
        open={confirmando}
        onOpenChange={setConfirmando}
        title="Exportar a Progress"
        description="Se generará el archivo para Progress. Una vez exportada, el plan de entregas ya no podrá modificarse."
        confirmLabel="Exportar"
        pendingLabel="Exportando…"
        isPending={isPending}
        onConfirm={() => {
          setConfirmando(false)
          onExportar()
        }}
      />
    </div>
  )
}
