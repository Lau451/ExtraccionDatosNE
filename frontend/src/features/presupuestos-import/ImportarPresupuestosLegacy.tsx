import { useState, type ChangeEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { subirPresupuestosProgress } from '@/lib/api/integracionProgress'
import { ImportarPresupuestosLegacyView } from './components/ImportarPresupuestosLegacyView'

/** Container de la pantalla de import (design "container-presentational
 * pattern"): sube el archivo tal como lo exporta Progress y el backend lo
 * decodifica, lo parsea y lo registra (odd/tasks/integracion-progress.md S4,
 * S5). Si el parseo tiene errores, el backend rechaza el archivo entero y
 * devuelve los errores por línea; si el mismo contenido ya se había recibido,
 * responde `duplicado` sin importar nada. */
export function ImportarPresupuestosLegacy() {
  const [archivo, setArchivo] = useState<File | null>(null)
  const mutation = useMutation({
    mutationFn: (seleccionado: File) => subirPresupuestosProgress(seleccionado),
  })

  function onSeleccionarArchivo(event: ChangeEvent<HTMLInputElement>) {
    mutation.reset()
    setArchivo(event.target.files?.[0] ?? null)
  }

  function onImportar() {
    if (!archivo) return
    mutation.mutate(archivo)
  }

  const recepcion = mutation.data
  const duplicado = recepcion?.estado === 'duplicado' ? { procesadoAt: recepcion.procesado_at } : null

  return (
    <ImportarPresupuestosLegacyView
      onSeleccionarArchivo={onSeleccionarArchivo}
      erroresValidacion={recepcion?.estado === 'error' ? recepcion.errores : []}
      duplicado={duplicado}
      onImportar={onImportar}
      puedeImportar={!!archivo}
      importando={mutation.isPending}
      errorImportacion={mutation.isError ? mutation.error.message : null}
      resultados={recepcion?.estado === 'procesado' ? recepcion.resultados : []}
    />
  )
}
