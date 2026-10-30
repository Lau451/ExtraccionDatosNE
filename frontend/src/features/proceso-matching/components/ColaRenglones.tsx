import type { Ref } from 'react'
import type { RenglonMatching } from '@/lib/api/matching'
import { ESTILO_ESTADO, etiquetaEstado } from '../presentacion'

function productoDelRenglon(renglon: RenglonMatching): { texto: string; tentativo: boolean } {
  if (renglon.producto) return { texto: renglon.producto.nombre, tentativo: false }
  if (renglon.estado_matching === 'sin_match') return { texto: 'Sin producto', tentativo: false }
  const mejor = renglon.candidatos[0]
  return mejor ? { texto: mejor.producto.nombre, tentativo: true } : { texto: 'Sin candidatos', tentativo: false }
}

interface Props {
  renglones: RenglonMatching[]
  seleccionadoId: string | null
  listaRef: Ref<HTMLUListElement>
  onSeleccionar: (itemProcesoId: string) => void
}

/** The queue of the matching screen (S11): one line per renglón with its
 * descripción, the producto it has or would get, and its estado. */
export function ColaRenglones({ renglones, seleccionadoId, listaRef, onSeleccionar }: Props) {
  return (
    <ul
      ref={listaRef}
      role="listbox"
      tabIndex={0}
      aria-label="Renglones del proceso"
      aria-activedescendant={seleccionadoId ? `renglon-${seleccionadoId}` : undefined}
      className="min-h-0 flex-1 overflow-y-auto focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
    >
      {renglones.map((renglon) => {
        const seleccionado = renglon.item_proceso_id === seleccionadoId
        const producto = productoDelRenglon(renglon)
        return (
          <li
            key={renglon.item_proceso_id}
            id={`renglon-${renglon.item_proceso_id}`}
            role="option"
            aria-selected={seleccionado}
            aria-label={`Renglón ${renglon.numero_renglon}`}
            ref={seleccionado ? (nodo) => nodo?.scrollIntoView?.({ block: 'nearest' }) : undefined}
            onClick={() => onSeleccionar(renglon.item_proceso_id)}
            className={`grid cursor-pointer grid-cols-[2rem_1fr_auto] items-center gap-2 border-b border-slate-100 px-4 py-2 text-sm ${
              seleccionado ? 'bg-sky-50 shadow-[inset_3px_0_0_var(--color-accent)]' : 'hover:bg-slate-50'
            }`}
          >
            <span className="text-xs tabular-nums text-slate-500">{renglon.numero_renglon}</span>
            <span className="min-w-0">
              <span className="block truncate text-slate-900">{renglon.descripcion}</span>
              <span className={`block truncate text-xs text-slate-500 ${producto.tentativo ? 'italic' : ''}`}>
                {producto.texto}
              </span>
            </span>
            <span
              className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${ESTILO_ESTADO[renglon.estado_matching]}`}
            >
              {etiquetaEstado(renglon)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
