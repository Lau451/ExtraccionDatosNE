import type { ChangeEvent } from 'react'
import type { ImportPresupuestoLegacyResultado } from '@/lib/api/pcp'
import type { ErrorParseoCsv } from '../parsearCsvPresupuestos'

export interface VistaPreviaCsv {
  presupuestos: number
  filas: number
}

interface Props {
  onSeleccionarArchivo: (event: ChangeEvent<HTMLInputElement>) => void
  errorLectura: string | null
  vistaPrevia: VistaPreviaCsv | null
  erroresValidacion: ErrorParseoCsv[]
  onImportar: () => void
  puedeImportar: boolean
  importando: boolean
  errorImportacion: string | null
  resultados: ImportPresupuestoLegacyResultado[]
}

/** Pura: toda la lógica (lectura de archivo, parseo, mutation) vive en el
 * container `ImportarPresupuestosLegacy`. Container-presentational split
 * pedido por la tarea T1 (odd/tasks/presupuestos-legacy-import-ui.md). */
export function ImportarPresupuestosLegacyView({
  onSeleccionarArchivo,
  errorLectura,
  vistaPrevia,
  erroresValidacion,
  onImportar,
  puedeImportar,
  importando,
  errorImportacion,
  resultados,
}: Props) {
  return (
    <main className="p-8">
      <header className="mb-6">
        <h1 className="text-balance text-xl font-semibold text-navy">Importar presupuestos legados</h1>
        <p className="text-sm text-slate-500">Carga del export CSV del sistema anterior (Progress)</p>
      </header>

      <label className="block max-w-md text-sm text-slate-600">
        Archivo CSV
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={onSeleccionarArchivo}
          className="mt-1 block w-full text-sm"
        />
      </label>

      {errorLectura ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {errorLectura}
        </p>
      ) : null}

      {vistaPrevia ? (
        <p className="mt-4 text-sm text-slate-700">
          {vistaPrevia.presupuestos} presupuestos, {vistaPrevia.filas} filas detectadas
        </p>
      ) : null}

      {erroresValidacion.length > 0 ? (
        <div className="mt-4 max-w-xl rounded-md border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-700">
            {erroresValidacion.length} {erroresValidacion.length === 1 ? 'error bloquea' : 'errores bloquean'} el
            import
          </p>
          <ul className="mt-2 space-y-1 text-sm text-red-700">
            {erroresValidacion.map((error) => (
              <li key={`${error.linea}-${error.mensaje}`}>
                Línea {error.linea}: {error.mensaje}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {errorImportacion ? (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {errorImportacion}
        </p>
      ) : null}

      <button
        type="button"
        onClick={onImportar}
        disabled={!puedeImportar || importando}
        className="mt-6 min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white disabled:opacity-50"
      >
        {importando ? 'Importando…' : 'Importar'}
      </button>

      {resultados.length > 0 ? (
        <table className="mt-6 w-full max-w-2xl text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-2 pr-4 font-medium">Número</th>
              <th className="py-2 pr-4 font-medium">Acción</th>
              <th className="py-2 pr-4 font-medium">Renglones procesados</th>
              <th className="py-2 pr-4 font-medium">Renglones sin producto</th>
            </tr>
          </thead>
          <tbody>
            {resultados.map((resultado) => (
              <tr key={resultado.presupuesto_id} className="border-b border-slate-100 text-slate-700">
                <td className="py-2 pr-4">{resultado.codigo_legacy}</td>
                <td className="py-2 pr-4">{resultado.accion}</td>
                <td className="py-2 pr-4">{resultado.renglones_procesados}</td>
                <td className="py-2 pr-4">{resultado.renglones_sin_producto}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </main>
  )
}
