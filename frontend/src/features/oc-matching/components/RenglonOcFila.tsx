import { useState } from 'react'
import type { RenglonOrdenCompra } from '@/lib/api/ocMatching'

interface Props {
  renglon: RenglonOrdenCompra
  seleccionado: boolean
  isPending: boolean
  onSeleccionar: () => void
  onConfirmar: (presupuestoItemId: string) => void
  onDeshacer: () => void
  onDescartar: () => void
}

const ETIQUETA_ESTADO: Record<RenglonOrdenCompra['estado'], string> = {
  pendiente: 'Pendiente',
  confirmado: 'Confirmado',
  sin_presupuesto: 'No está en el presupuesto',
}

/** Una fila de la columna derecha (design.md D4/D13, spec
 * oc-presupuesto-vinculacion). Confirmación granular por renglón: un único
 * candidato deja "Confirmar" habilitado sin preseleccionar nada; varios
 * candidatos exigen elegir uno primero (mismo patrón de radios sin
 * preselección que `OrdenCompraSelector` para CUIT compartido); cero
 * candidatos deja el renglón `pendiente`, visible, y NO bloquea confirmar los
 * demás renglones de la misma OC. */
export function RenglonOcFila({
  renglon,
  seleccionado,
  isPending,
  onSeleccionar,
  onConfirmar,
  onDeshacer,
  onDescartar,
}: Props) {
  const [candidatoElegidoId, setCandidatoElegidoId] = useState<string | null>(null)

  return (
    <div
      role="listitem"
      onClick={onSeleccionar}
      className={`rounded-md border p-3 text-sm ${
        seleccionado ? 'border-navy bg-navy/5' : 'border-slate-200'
      }`}
    >
      <div className="flex items-center justify-between">
        <p className="font-medium text-slate-900">{renglon.descripcion}</p>
        <span className="text-xs font-medium text-slate-500">{ETIQUETA_ESTADO[renglon.estado]}</span>
      </div>
      <p className="text-slate-600">
        Cant. {renglon.cantidad} — ${renglon.precio_unitario}
      </p>

      {renglon.estado === 'confirmado' && (
        <div className="mt-2 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            Vínculo {renglon.vinculo_origen === 'manual' ? 'manual' : 'por precio exacto'}
          </p>
          <button
            type="button"
            disabled={isPending}
            onClick={(evento) => {
              evento.stopPropagation()
              onDeshacer()
            }}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-40"
          >
            Deshacer
          </button>
        </div>
      )}

      {renglon.estado === 'sin_presupuesto' && (
        <div className="mt-2 flex items-center justify-between">
          <p className="text-xs text-slate-500">Un humano declaró que este renglón no está en el presupuesto.</p>
          <button
            type="button"
            disabled={isPending}
            onClick={(evento) => {
              evento.stopPropagation()
              onDeshacer()
            }}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-40"
          >
            Deshacer
          </button>
        </div>
      )}

      {renglon.estado === 'pendiente' && (
        <div className="mt-2 space-y-2" onClick={(evento) => evento.stopPropagation()}>
          {renglon.candidatos.length === 0 && (
            <p className="text-xs text-slate-500">
              Pendiente — ningún renglón del presupuesto coincide en precio.
            </p>
          )}

          {renglon.candidatos.length === 1 && (
            <button
              type="button"
              disabled={isPending}
              onClick={() => onConfirmar(renglon.candidatos[0].presupuesto_item_id)}
              className="rounded-md bg-navy px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
            >
              Confirmar
            </button>
          )}

          {renglon.candidatos.length > 1 && (
            <fieldset className="space-y-1">
              <legend className="sr-only">Candidatos ordenados por similitud de descripción</legend>
              {renglon.candidatos.map((candidato) => (
                <label key={candidato.presupuesto_item_id} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`candidato-${renglon.oc_item_id}`}
                    checked={candidatoElegidoId === candidato.presupuesto_item_id}
                    onChange={() => setCandidatoElegidoId(candidato.presupuesto_item_id)}
                  />
                  <span>
                    {candidato.presupuesto_item_id}
                    {candidato.similitud !== null ? ` — ${candidato.similitud}% similitud` : ''}
                  </span>
                </label>
              ))}
              <button
                type="button"
                disabled={isPending || !candidatoElegidoId}
                onClick={() => candidatoElegidoId && onConfirmar(candidatoElegidoId)}
                className="rounded-md bg-navy px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
              >
                Confirmar
              </button>
            </fieldset>
          )}

          <button
            type="button"
            disabled={isPending}
            onClick={onDescartar}
            className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-40"
          >
            No está en el presupuesto
          </button>
        </div>
      )}
    </div>
  )
}
