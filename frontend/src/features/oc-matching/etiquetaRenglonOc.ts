import type { RenglonOrdenCompra } from '@/lib/api/ocMatching'

/** Número de renglón a mostrar en pantalla (spec oc-numero-renglon-documento):
 * el impreso en el documento del cliente cuando la extracción lo detectó, o
 * si no el ordinal posicional 1..N que el backend asigna al confirmar
 * (D13.1, `oc_items.numero_renglon`). Usado tanto en la columna de OC como
 * en el botón de vínculo manual de la columna de presupuesto -- misma
 * etiqueta en los dos lugares. */
export function etiquetaRenglonOc(
  renglon: Pick<RenglonOrdenCompra, 'numero_renglon' | 'numero_renglon_documento'>,
): string {
  return renglon.numero_renglon_documento ?? String(renglon.numero_renglon)
}
