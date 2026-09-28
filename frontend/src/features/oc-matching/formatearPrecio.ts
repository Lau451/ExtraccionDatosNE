/** Precio a mostrar en la pantalla de matching: siempre dos decimales, para
 * que 3093.7 no se vea como "$3093.7" ni 381 como "$381". Los precios llegan
 * como number ya parseado en el borde del API client (`ocMatching.ts`). */
export function formatearPrecio(precio: number): string {
  return precio.toFixed(2)
}
