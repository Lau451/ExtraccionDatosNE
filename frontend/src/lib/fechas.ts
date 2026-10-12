/** Fecha/hora ISO en formato legible es-AR; si no es parseable, devuelve el texto original. */
export function fechaLegible(iso: string): string {
  const fecha = new Date(iso)
  return Number.isNaN(fecha.getTime()) ? iso : fecha.toLocaleString('es-AR')
}
