/** Espejo puro de `sugerir_plan_renglon` / `repartir_cantidad`
 * (services/presupuestacion/{oc_entregas,extraccion}/service.py, D8 + T3).
 * Usado para recalcular la sugerencia en el cliente cuando el usuario cambia
 * la cantidad de entregas (N) -- el GET del backend solo sugiere para
 * `cantidad_entregas_sugerida`, así que un cambio de N no pega otra vez al
 * servidor. */

/** Espejo de `repartir_cantidad` (extraccion/service.py, D8): reparte
 * `cantidad` entre `entregas` lo más parejo posible. Entero -> las primeras
 * `cantidad % entregas` reciben `base + 1`, el resto `base`. Decimal -> las
 * primeras `entregas - 1` reciben la parte entera truncada a centésimos, la
 * última se lleva el resto (para no arrastrar el error de redondeo).
 * Invariante: `sum(resultado) === cantidad`, siempre. */
function repartirCantidad(cantidad: number, entregas: number): number[] {
  if (entregas < 1) return []
  if (Number.isInteger(cantidad)) {
    const base = Math.floor(cantidad / entregas)
    const resto = cantidad - base * entregas
    return Array.from({ length: entregas }, (_, indice) => (indice < resto ? base + 1 : base))
  }
  const base = Math.floor((cantidad / entregas) * 100) / 100
  const partes = Array.from({ length: entregas - 1 }, () => base)
  const ultima = Math.round((cantidad - base * (entregas - 1)) * 100) / 100
  return [...partes, ultima]
}

/** Espejo de `sugerir_plan_renglon` (oc_entregas/service.py, T3): sugerencia
 * de reparto para UN renglón confirmado. Índice i == entrega i+1.
 *
 * Con presentación conocida (`unidadesPorPresentacion`): `packs = floor(cantidad / u)`
 * se reparte parejo entre las N entregas con `repartirCantidad` (las primeras
 * reciben un pack de más), cada parte se multiplica por `u`, y el resto
 * (`cantidad - packs*u`) se suma a la ÚLTIMA entrega.
 *
 * Sin presentación conocida (null/undefined/<=0): reparto liso con
 * `repartirCantidad`, sin noción de pack.
 *
 * Ejemplos (design.md D8 + T3): (100, 25, 3) -> [50, 25, 25];
 * (110, 25, 3) -> [50, 25, 35]. */
export function sugerirPlanRenglon(
  cantidad: number,
  unidadesPorPresentacion: number | null | undefined,
  entregas: number,
): number[] {
  if (entregas < 1) return []
  if (!unidadesPorPresentacion || unidadesPorPresentacion <= 0) {
    return repartirCantidad(cantidad, entregas)
  }

  const u = unidadesPorPresentacion
  const packs = Math.floor(cantidad / u)
  const resto = cantidad - packs * u

  const cantidades = repartirCantidad(packs, entregas).map((parte) => parte * u)
  cantidades[cantidades.length - 1] += resto
  return cantidades
}

/** Espejo de `_advertencias_divisibilidad` (oc_entregas/service.py, T3): el
 * múltiplo de `unidadesPorPresentacion` más cercano por abajo de `cantidad`,
 * o la presentación completa cuando ese múltiplo da cero. */
export function sugerirCantidadDivisible(cantidad: number, unidadesPorPresentacion: number): number {
  const sugerida = Math.floor(cantidad / unidadesPorPresentacion) * unidadesPorPresentacion
  return sugerida === 0 ? unidadesPorPresentacion : sugerida
}
