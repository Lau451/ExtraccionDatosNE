import type { RenglonOrdenCompra, RenglonPresupuesto } from '@/lib/api/ocMatching'
import { AvisoReutilizacion } from './AvisoReutilizacion'

interface Props {
  renglones: RenglonPresupuesto[]
  /** Renglón de OC actualmente resaltado en la columna derecha (D12, único
   * estado local del container): permite marcar del lado del presupuesto qué
   * filas son candidatas de ese renglón de OC. */
  renglonOcSeleccionado: RenglonOrdenCompra | null
}

/** Columna izquierda de la pantalla de matching (design.md § Forma del
 * frontend): descripción/cantidad/precio/estado por `RenglonPresupuesto`,
 * integrando el aviso de reutilización N:1 por fila (D5). */
export function ColumnaPresupuesto({ renglones, renglonOcSeleccionado }: Props) {
  const idsCandidatos = new Set(
    renglonOcSeleccionado?.candidatos.map((candidato) => candidato.presupuesto_item_id) ?? [],
  )

  return (
    <section aria-label="Renglones del presupuesto" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-700">Presupuesto</h2>
      <div role="list" className="space-y-2">
        {renglones.map((renglon) => (
          <div
            key={renglon.presupuesto_item_id}
            role="listitem"
            className={`rounded-md border p-3 text-sm ${
              idsCandidatos.has(renglon.presupuesto_item_id)
                ? 'border-navy bg-navy/5'
                : 'border-slate-200'
            }`}
          >
            <p className="font-medium text-slate-900">{renglon.descripcion}</p>
            <p className="text-slate-600">
              Cant. {renglon.cantidad_ofertada ?? '—'} — ${renglon.precio_unitario}
            </p>
            <AvisoReutilizacion renglon={renglon} />
          </div>
        ))}
      </div>
    </section>
  )
}
