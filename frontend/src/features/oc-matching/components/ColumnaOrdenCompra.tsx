import type { RenglonOrdenCompra } from '@/lib/api/ocMatching'
import { RenglonOcFila } from './RenglonOcFila'

interface Props {
  renglones: RenglonOrdenCompra[]
  renglonSeleccionadoId: string | null
  isPending: boolean
  onSeleccionar: (ocItemId: string) => void
  onConfirmar: (ocItemId: string, presupuestoItemId: string) => void
  onDeshacer: (ocItemId: string) => void
  onDescartar: (ocItemId: string) => void
}

/** Columna derecha de la pantalla de matching (design.md § Forma del
 * frontend): un `RenglonOcFila` por renglón de OC, con confirmación granular
 * por renglón -- click en un renglón lo resalta, sin exigir que los demás se
 * confirmen antes (spec § "Confirmar un renglón no exige confirmar los demás
 * primero"). */
export function ColumnaOrdenCompra({
  renglones,
  renglonSeleccionadoId,
  isPending,
  onSeleccionar,
  onConfirmar,
  onDeshacer,
  onDescartar,
}: Props) {
  return (
    <section aria-label="Renglones de la orden de compra" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-700">Orden de compra</h2>
      <div role="list" className="space-y-2">
        {renglones.map((renglon) => (
          <RenglonOcFila
            key={renglon.oc_item_id}
            renglon={renglon}
            seleccionado={renglon.oc_item_id === renglonSeleccionadoId}
            isPending={isPending}
            onSeleccionar={() => onSeleccionar(renglon.oc_item_id)}
            onConfirmar={(presupuestoItemId) => onConfirmar(renglon.oc_item_id, presupuestoItemId)}
            onDeshacer={() => onDeshacer(renglon.oc_item_id)}
            onDescartar={() => onDescartar(renglon.oc_item_id)}
          />
        ))}
      </div>
    </section>
  )
}
