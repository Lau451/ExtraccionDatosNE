import type { Ref } from 'react'
import type { ProductoResumen, RenglonMatching } from '@/lib/api/matching'
import { ESTILO_ESTADO, etiquetaEstado, formatearCantidad, porcentaje } from '../presentacion'
import { ProductoBuscador } from './ProductoBuscador'
import { Tecla } from './Tecla'

/** Candidatos reachable with the number keys 1-5 (S11). */
export const CANDIDATOS_CON_TECLA = 5

interface Props {
  renglon: RenglonMatching
  total: number
  textoBusqueda: string
  onTextoBusqueda: (texto: string) => void
  buscadorRef: Ref<HTMLInputElement>
  onConfirmar: (producto: ProductoResumen) => void
  onSinMatch: () => void
  onSalirDelBuscador: () => void
}

/** Decision panel of the selected renglón (S10, S11): its candidatos (best
 * first, numbered for the keyboard), the catalog search and sin match. */
export function PanelRenglon({
  renglon,
  total,
  textoBusqueda,
  onTextoBusqueda,
  buscadorRef,
  onConfirmar,
  onSinMatch,
  onSalirDelBuscador,
}: Props) {
  const elegidoId = renglon.producto?.id ?? null

  return (
    <section aria-label="Renglón elegido" className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-8 py-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Renglón {renglon.numero_renglon} de {total}
        </p>
        <h2 className="mt-1 mb-2 text-xl font-semibold text-slate-900">{renglon.descripcion}</h2>
        <div className="flex items-center gap-4 text-sm text-slate-600">
          <span>
            Cantidad <span className="font-semibold tabular-nums">{formatearCantidad(renglon.cantidad)}</span>
          </span>
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${ESTILO_ESTADO[renglon.estado_matching]}`}
          >
            {etiquetaEstado(renglon)}
          </span>
        </div>
      </div>

      {renglon.candidatos.length > 0 ? (
        <ul aria-label="Candidatos" className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200">
          {renglon.candidatos.map((candidato, indice) => {
            const elegido = candidato.producto.id === elegidoId
            const mejor = indice === 0 && !elegidoId
            const tecla = indice < CANDIDATOS_CON_TECLA ? String(indice + 1) : null
            return (
              <li key={candidato.producto.id}>
                <button
                  type="button"
                  aria-label={`Confirmar ${candidato.producto.nombre} (${candidato.producto.codigo_interno}) ${porcentaje(candidato.confianza)}`}
                  aria-keyshortcuts={tecla ?? undefined}
                  onClick={() => onConfirmar(candidato.producto)}
                  className={`grid w-full grid-cols-[1.75rem_1fr_7.5rem_6.5rem] items-center gap-3 px-4 py-3 text-left text-sm text-slate-900 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${
                    elegido ? 'bg-emerald-50' : mejor ? 'bg-sky-50' : 'bg-white hover:bg-slate-50'
                  }`}
                >
                  <span>{tecla && <Tecla>{tecla}</Tecla>}</span>
                  <span>
                    <span className="font-medium">{candidato.producto.nombre}</span>
                    <span className="ml-2 font-mono text-xs text-slate-500">{candidato.producto.codigo_interno}</span>
                  </span>
                  <span className="flex items-center gap-2 text-xs tabular-nums text-slate-600">
                    <span className="h-1.5 flex-1 rounded-full bg-slate-100">
                      <span
                        className="block h-full rounded-full bg-accent"
                        style={{ width: `${Math.min(100, Number(candidato.confianza))}%` }}
                      />
                    </span>
                    {porcentaje(candidato.confianza)}
                  </span>
                  <span className="text-right text-xs text-slate-500">
                    {elegido ? 'Elegido' : mejor ? 'Enter confirma' : ''}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">El matching no encontró candidatos. Buscá en el catálogo.</p>
      )}

      <ProductoBuscador
        key={renglon.item_proceso_id}
        texto={textoBusqueda}
        onTexto={onTextoBusqueda}
        inputRef={buscadorRef}
        onElegir={onConfirmar}
        onSalir={onSalirDelBuscador}
      />

      {renglon.estado_matching !== 'sin_match' && (
        <div>
          <button
            type="button"
            aria-label="Marcar sin match"
            aria-keyshortcuts="Shift"
            onClick={onSinMatch}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Sin match <Tecla>Shift</Tecla>
          </button>
        </div>
      )}

      <p className="mt-auto flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-200 pt-3 text-xs text-slate-500">
        <span>
          <Tecla>↑</Tecla> <Tecla>↓</Tecla> moverse
        </span>
        <span>
          <Tecla>Enter</Tecla> confirmar el mejor
        </span>
        <span>
          <Tecla>1</Tecla>–<Tecla>{CANDIDATOS_CON_TECLA}</Tecla> elegir candidato
        </span>
        <span>
          <Tecla>Shift</Tecla> sin match
        </span>
        <span>Escribir una letra busca en el catálogo</span>
        <span>
          <Tecla>Tab</Tecla> vuelve a los renglones
        </span>
        <span>
          <Tecla>Ctrl</Tecla>+<Tecla>Z</Tecla> volver al último
        </span>
        <span>Al decidir pasa solo al siguiente</span>
      </p>
    </section>
  )
}
