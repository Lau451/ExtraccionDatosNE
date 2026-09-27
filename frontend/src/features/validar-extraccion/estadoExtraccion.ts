import type { ExtraccionResumen } from '@/lib/api/extracciones'

/** Decisión del usuario (2026-09-26, `odd/tasks/validar-extraccion-organizacion.md`)
 * -- un único estado derivado por fila, combinando `status` (T1) y `validado`
 * (ya existía). `validado=true` siempre gana: una extracción validada no
 * vuelve a mostrarse como "procesada" aunque su status subyacente siga
 * siendo 'completed'/'partial'. */
export type EstadoDerivado = 'procesando' | 'procesado' | 'procesado_advertencias' | 'error' | 'validada'

/** Orden estable para pintar chips/leyendas -- mismo orden que la decisión
 * del usuario y que `ESTADO_META` abajo. */
export const ESTADOS_DERIVADOS: readonly EstadoDerivado[] = [
  'procesando',
  'procesado',
  'procesado_advertencias',
  'error',
  'validada',
]

type ExtraccionParaEstado = Pick<ExtraccionResumen, 'status' | 'validado'>

/** Pura y testeada aparte (T2): la deriva de "qué le muestro al usuario" es
 * la única fuente de verdad para el badge de cada fila, los chips de filtro
 * y el guard de qué filas son seleccionables/tienen link de revisión. */
export function estadoDerivadoDe(extraccion: ExtraccionParaEstado): EstadoDerivado {
  if (extraccion.validado) return 'validada'

  switch (extraccion.status) {
    case 'processing':
      return 'procesando'
    case 'completed':
      return 'procesado'
    case 'partial':
      return 'procesado_advertencias'
    case 'failed':
      return 'error'
    default:
      // Defensivo: un status que el frontend no reconoce (dato inesperado
      // desde el backend) se trata como "necesita atención", nunca como un
      // estado sano silencioso.
      return 'error'
  }
}

/** Solo `completed`/`partial` sin validar son validables (`ESTADOS_VALIDABLES`
 * en services/presupuestacion/extraccion/models.py) -- el guard del backend
 * no cambia con esta tarea; este helper es el espejo de lectura para decidir
 * qué filas ofrecen el link "Revisar" o el checkbox de selección de OC. */
export function esEstadoValidable(estado: EstadoDerivado): boolean {
  return estado === 'procesado' || estado === 'procesado_advertencias'
}

/** T3 -- orden de "menos avanzado" (decisión de usuario, 2026-09-27) para el
 * estado agregado del encabezado de un grupo de OC agrupadas: si todos los
 * miembros comparten el mismo estado derivado, ese es el estado del grupo;
 * si no, gana el que aparece antes en este orden. Distinto de
 * `ESTADOS_DERIVADOS` (ese es el orden de los chips de filtro, no una
 * prioridad). */
const ORDEN_ESTADO_GRUPO: readonly EstadoDerivado[] = [
  'procesando',
  'error',
  'procesado_advertencias',
  'procesado',
  'validada',
]

/** Pura y testeada aparte (T3): estado agregado para el badge del encabezado
 * colapsable de un grupo. `estados` es la lista de `estadoDerivadoDe(...)`
 * ya calculados para cada miembro del grupo. */
export function estadoGrupoDe(estados: EstadoDerivado[]): EstadoDerivado {
  return estados.reduce((menosAvanzado, actual) =>
    ORDEN_ESTADO_GRUPO.indexOf(actual) < ORDEN_ESTADO_GRUPO.indexOf(menosAvanzado) ? actual : menosAvanzado,
  )
}

export const ESTADO_META: Record<EstadoDerivado, { label: string; badgeClass: string; pulso?: boolean }> = {
  // El texto es siempre el indicador principal (WCAG 1.4.1); el color es
  // refuerzo. Mismo criterio de color que `RecentCard.tsx` para
  // procesando/error; advertencias usa `orange` (no `amber`) para no
  // confundirse visualmente con "procesando" pese a compartir familia de
  // color cálido.
  procesando: { label: 'Procesando', badgeClass: 'bg-amber-100 text-amber-700', pulso: true },
  procesado: { label: 'Procesado', badgeClass: 'bg-sky-100 text-sky-700' },
  procesado_advertencias: { label: 'Procesado con advertencias', badgeClass: 'bg-orange-100 text-orange-800' },
  error: { label: 'Error', badgeClass: 'bg-red-100 text-red-700' },
  validada: { label: 'Validada', badgeClass: 'bg-emerald-100 text-emerald-700' },
}
