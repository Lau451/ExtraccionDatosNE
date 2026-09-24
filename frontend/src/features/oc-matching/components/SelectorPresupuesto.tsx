import type { PresupuestosCandidatosOut } from '@/lib/api/ocMatching'

interface Props {
  data: PresupuestosCandidatosOut
  /** El presupuesto realmente elegido para esta sesión (design.md D8: vive en
   * la URL/los vínculos, nunca en estado local de React de este componente).
   * `null` mientras nadie eligió explícitamente -- el sugerido NUNCA viene
   * pre-marcado, ni siquiera con un único candidato (spec § "Selección
   * explícita del presupuesto por el usuario"). */
  presupuestoIdSeleccionado: string | null
  onSeleccionar: (presupuestoId: string) => void
}

/** Lista de presupuestos candidatos rankeados (design.md D2, spec
 * oc-presupuesto-candidato). El orden ya lo resuelve el backend -- el sugerido
 * es `candidatos[0]` -- este componente solo distingue los dos estados vacíos
 * y nunca preselecciona nada por sí mismo. */
export function SelectorPresupuesto({ data, presupuestoIdSeleccionado, onSeleccionar }: Props) {
  if (data.presupuestos_del_cliente === 0) {
    return (
      <p className="text-sm text-slate-500">
        El cliente no tiene presupuestos cargados en el sistema.
      </p>
    )
  }

  if (data.candidatos.length === 0) {
    const plural = data.presupuestos_del_cliente === 1 ? '' : 's'
    return (
      <p className="text-sm text-slate-500">
        El cliente tiene {data.presupuestos_del_cliente} presupuesto{plural} cargado{plural}, pero
        ninguno coincide en precio con esta orden de compra.
      </p>
    )
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm text-slate-600">Presupuestos candidatos:</legend>
      {data.candidatos.map((candidato) => (
        <label
          key={candidato.presupuesto_id}
          className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm"
        >
          <input
            type="radio"
            name="presupuesto-candidato"
            checked={presupuestoIdSeleccionado === candidato.presupuesto_id}
            onChange={() => onSeleccionar(candidato.presupuesto_id)}
          />
          <span>
            {candidato.numero_presupuesto ?? candidato.nombre_proceso}
            {' — '}
            {candidato.renglones_oc_con_coincidencia}/{candidato.renglones_oc_totales} coincidencias
            {candidato.presupuesto_id === data.presupuesto_sugerido_id ? ' (sugerido)' : ''}
          </span>
        </label>
      ))}
    </fieldset>
  )
}
