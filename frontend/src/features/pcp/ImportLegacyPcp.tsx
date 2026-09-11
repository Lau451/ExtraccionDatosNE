import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { importarPcpLegacy } from '@/lib/api/pcp'
import type { FilaImportPcpLegacy, ImportPcpLegacyResultado } from '@/lib/api/pcp'

/** Cuenta los resultados de import por acción. Función pura, sin dependencias
 * de React, para mantener la lógica de conteo fácil de verificar por separado
 * de la presentación. */
function contarPorAccion(resultados: ImportPcpLegacyResultado[]) {
  return {
    creados: resultados.filter((resultado) => resultado.accion === 'creado').length,
    actualizados: resultados.filter((resultado) => resultado.accion === 'actualizado').length,
  }
}

/** Formatea un conteo con singular/plural evitando repetir el ternario en
 * cada línea del resumen. */
function formatearConteo(cantidad: number, singular: string, plural: string): string {
  return `${cantidad} PCP ${cantidad === 1 ? singular : plural}`
}

/** El formato exacto de parseo (CSV vs JSON) queda abierto por spec/design
 * (spec `pcp-ui-legacy-import` solo exige el resultado, no el formato de
 * archivo). Se elige JSON porque es un `JSON.parse` trivial sobre
 * `File.text()`; sección 8.3 puede reemplazar este parseo sin tocar el
 * contrato con `importarPcpLegacy`. */
async function parsearArchivoLegado(archivo: File): Promise<FilaImportPcpLegacy[]> {
  const texto = await archivo.text()
  return JSON.parse(texto) as FilaImportPcpLegacy[]
}

export function ImportLegacyPcp() {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [errorLectura, setErrorLectura] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: (filas: FilaImportPcpLegacy[]) => importarPcpLegacy(filas),
  })

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!archivo) return
    setErrorLectura(null)
    try {
      const filas = await parsearArchivoLegado(archivo)
      mutation.mutate(filas)
    } catch {
      setErrorLectura('No se pudo leer el archivo seleccionado.')
    }
  }

  const resultados = mutation.data ?? []
  const { creados, actualizados } = contarPorAccion(resultados)

  return (
    <main className="p-8">
      <header className="mb-6">
        <h1 className="text-balance text-xl font-semibold text-navy">Importar PCP legado</h1>
        <p className="text-sm text-slate-500">Carga masiva idempotente desde el sistema anterior</p>
      </header>
      <form onSubmit={handleSubmit} className="max-w-md space-y-4">
        <label className="block text-sm text-slate-600">
          Archivo legado
          <input
            type="file"
            onChange={(event) => setArchivo(event.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-sm"
          />
        </label>
        {errorLectura ? <p role="alert" className="text-sm text-red-600">{errorLectura}</p> : null}
        {mutation.isError ? <p role="alert" className="text-sm text-red-600">No se pudo importar el archivo.</p> : null}
        <button
          type="submit"
          disabled={!archivo || mutation.isPending}
          className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white disabled:opacity-50"
        >
          {mutation.isPending ? 'Importando…' : 'Importar'}
        </button>
      </form>
      {mutation.isSuccess ? (
        <div className="mt-6 space-y-1 text-sm text-slate-700">
          {creados > 0 ? <p>{formatearConteo(creados, 'creado', 'creados')}</p> : null}
          {actualizados > 0 ? <p>{formatearConteo(actualizados, 'actualizado', 'actualizados')}</p> : null}
          {creados === 0 && actualizados === 0 ? <p>No se procesó ningún registro.</p> : null}
        </div>
      ) : null}
    </main>
  )
}
