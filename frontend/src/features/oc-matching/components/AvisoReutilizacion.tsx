import type { RenglonPresupuesto } from '@/lib/api/ocMatching'

interface Props {
  renglon: RenglonPresupuesto
}

/** Aviso suave de reutilización N:1 (design.md D5, spec § "Relación N:1
 * permitida, con aviso no bloqueante"). Puramente informativo: se calcula en
 * cada lectura del servidor y NUNCA deshabilita ningún control -- ni el propio
 * componente ofrece botones que pudieran hacerlo. */
export function AvisoReutilizacion({ renglon }: Props) {
  const reutilizado = renglon.renglones_oc_vinculados >= 2
  const excedeCantidad =
    renglon.cantidad_ofertada !== null && renglon.cantidad_vinculada > renglon.cantidad_ofertada

  if (!reutilizado && !excedeCantidad) {
    return null
  }

  return (
    <div className="mt-1 space-y-0.5 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-700">
      {reutilizado && (
        <p>
          Este renglón ya está vinculado desde {renglon.renglones_oc_vinculados} renglones de orden de
          compra
          {renglon.renglones_oc_vinculados_otras_oc > 0 ? ' (incluye otras órdenes de compra)' : ''}.
        </p>
      )}
      {excedeCantidad && (
        <p>
          La cantidad vinculada ({renglon.cantidad_vinculada}) supera la cantidad ofertada (
          {renglon.cantidad_ofertada}).
        </p>
      )}
    </div>
  )
}
