import { useState, type ChangeEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { importarPresupuestosLegacy } from '@/lib/api/pcp'
import type { FilaImportPresupuestoLegacy } from '@/lib/api/pcp'
import { parsearCsvPresupuestos, type ResultadoParseoCsvPresupuestos } from './parsearCsvPresupuestos'
import { ImportarPresupuestosLegacyView } from './components/ImportarPresupuestosLegacyView'

function contarPresupuestos(filas: FilaImportPresupuestoLegacy[]): number {
  return new Set(filas.map((fila) => fila.numero_presupuesto)).size
}

/** Container de la pantalla de import (design "container-presentational
 * pattern"): lee el `File`, parsea el CSV en el browser con
 * `parsearCsvPresupuestos` (función pura) y solo llama a la API cuando el
 * parseo no tiene errores -- "nothing is sent if there are errors" (feature
 * doc Decisions). */
export function ImportarPresupuestosLegacy() {
  const [errorLectura, setErrorLectura] = useState<string | null>(null)
  const [parseo, setParseo] = useState<ResultadoParseoCsvPresupuestos | null>(null)
  const mutation = useMutation({
    mutationFn: (filas: FilaImportPresupuestoLegacy[]) => importarPresupuestosLegacy(filas),
  })

  async function onSeleccionarArchivo(event: ChangeEvent<HTMLInputElement>) {
    const archivo = event.target.files?.[0] ?? null
    mutation.reset()
    setParseo(null)
    setErrorLectura(null)
    if (!archivo) return
    try {
      const contenido = await archivo.text()
      setParseo(parsearCsvPresupuestos(contenido))
    } catch {
      setErrorLectura('No se pudo leer el archivo seleccionado.')
    }
  }

  function onImportar() {
    if (!parseo || parseo.errores.length > 0 || parseo.filas.length === 0) return
    mutation.mutate(parseo.filas)
  }

  const vistaPrevia = parseo && parseo.errores.length === 0
    ? { presupuestos: contarPresupuestos(parseo.filas), filas: parseo.filas.length }
    : null
  const puedeImportar = !!parseo && parseo.errores.length === 0 && parseo.filas.length > 0

  return (
    <ImportarPresupuestosLegacyView
      onSeleccionarArchivo={onSeleccionarArchivo}
      errorLectura={errorLectura}
      vistaPrevia={vistaPrevia}
      erroresValidacion={parseo?.errores ?? []}
      onImportar={onImportar}
      puedeImportar={puedeImportar}
      importando={mutation.isPending}
      errorImportacion={mutation.isError ? mutation.error.message : null}
      resultados={mutation.data ?? []}
    />
  )
}
