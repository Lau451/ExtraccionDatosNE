/** UI label of a proceso comercial's `clase`. */
export const CLASE_LEGIBLE: Record<string, string> = {
  licitacion: 'Licitación',
  cotizacion: 'Directa',
}

export function contar(cantidad: number, singular: string, plural: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : plural}`
}
