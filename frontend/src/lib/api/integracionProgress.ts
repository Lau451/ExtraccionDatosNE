import type { ImportPresupuestoLegacyResultado } from './pcp'
import { presupuestacionFetch } from './presupuestacion'

/** Espejo de `integracion_progress/registro/models.py::ErrorLinea`. `linea` 0 es un
 * error del archivo entero (por ejemplo, la entrega a PCP falló). */
export interface ErrorLineaArchivo {
  linea: number
  mensaje: string
}

export type EstadoRecepcion = 'procesado' | 'duplicado' | 'error'

/** Espejo de `integracion_progress/models.py::RecepcionPresupuestosOut`. */
export interface RecepcionPresupuestos {
  estado: EstadoRecepcion
  registro_id: string
  nombre_archivo: string
  /** En `duplicado`, cuándo se procesó el archivo original (null si sigue en curso). */
  procesado_at: string | null
  /** Solo en `error`: errores por línea; no se importó nada. */
  errores: ErrorLineaArchivo[]
  /** Solo en `procesado`: un resultado por presupuesto. */
  resultados: ImportPresupuestoLegacyResultado[]
}

/** POST /integracion-progress/presupuestos: sube el CSV tal como lo exporta Progress
 * (multipart, sin `Content-Type` para que el navegador ponga el boundary). El backend
 * lo parsea, lo deduplica por contenido y lo importa en PCP. Errores de la entrega
 * (`ApiError`, `detail` del backend tal cual), p. ej. 404 cliente inexistente. */
export function subirPresupuestosProgress(archivo: File): Promise<RecepcionPresupuestos> {
  const body = new FormData()
  body.append('archivo', archivo)
  return presupuestacionFetch<RecepcionPresupuestos>('/integracion-progress/presupuestos', {
    method: 'POST',
    body,
  })
}
