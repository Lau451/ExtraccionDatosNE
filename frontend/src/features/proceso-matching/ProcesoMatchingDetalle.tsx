import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  confirmarMatching,
  marcarSinMatch,
  obtenerMatchingProceso,
  type MatchingProceso,
  type ProductoResumen,
  type RenglonMatching,
} from '@/lib/api/matching'
import { ColaRenglones } from './components/ColaRenglones'
import { CANDIDATOS_CON_TECLA, PanelRenglon } from './components/PanelRenglon'
import { estaResuelto } from './presentacion'
import { CLASE_LEGIBLE, contar } from './textos'

type Filtro = 'abiertos' | 'todos' | 'resueltos'

const FILTROS: { valor: Filtro; etiqueta: string }[] = [
  { valor: 'abiertos', etiqueta: 'Por resolver' },
  { valor: 'todos', etiqueta: 'Todos' },
  { valor: 'resueltos', etiqueta: 'Resueltos' },
]

const DURACION_AVISO_MS = 4000

type Decision = { tipo: 'confirmar'; producto: ProductoResumen } | { tipo: 'sin_match' }

interface VariablesDecision {
  renglon: RenglonMatching
  decision: Decision
}

function pasaFiltro(renglon: RenglonMatching, filtro: Filtro): boolean {
  if (filtro === 'todos') return true
  return (filtro === 'resueltos') === estaResuelto(renglon)
}

/** The renglón as it will be once the backend applies the decision, so the
 * queue moves on without waiting for the request (S11). */
function aplicarDecision(renglon: RenglonMatching, decision: Decision): RenglonMatching {
  if (decision.tipo === 'sin_match') {
    return {
      ...renglon,
      estado_matching: 'sin_match',
      producto: null,
      candidatos: renglon.candidatos.map((c) => ({ ...c, elegido: false })),
    }
  }
  return {
    ...renglon,
    estado_matching: 'confirmado',
    producto: decision.producto,
    candidatos: renglon.candidatos.map((c) => ({ ...c, elegido: c.producto.id === decision.producto.id })),
  }
}

function reemplazarRenglon(
  matching: MatchingProceso | undefined,
  renglon: RenglonMatching,
): MatchingProceso | undefined {
  if (!matching) return matching
  return {
    ...matching,
    renglones: matching.renglones.map((r) => (r.item_proceso_id === renglon.item_proceso_id ? renglon : r)),
  }
}

function esCampoDeTexto(elemento: EventTarget | null): boolean {
  return (
    elemento instanceof HTMLElement &&
    elemento.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]') !== null
  )
}

interface Props {
  procesoId: string
}

/** Matching screen of one proceso comercial as a keyboard queue (presupuestador-v1
 * T3d, S10/S11): the renglones on the left, the selected one's candidatos,
 * catalog search and sin match on the right. Enter confirms the best candidato,
 * 1-5 another one, Shift alone marks sin match, any letter goes to the search,
 * Tab comes back from it. Decisions apply at once (optimistic) and the queue
 * moves on; a failed one is put back and shown. */
export function ProcesoMatchingDetalle({ procesoId }: Props) {
  const queryClient = useQueryClient()
  const [filtro, setFiltro] = useState<Filtro>('abiertos')
  const [seleccionadoId, setSeleccionadoId] = useState<string | null>(null)
  const [textoBusqueda, setTextoBusqueda] = useState('')
  const [ultimo, setUltimo] = useState<{ itemProcesoId: string; texto: string } | null>(null)
  const [avisoVisible, setAvisoVisible] = useState(false)
  const listaRef = useRef<HTMLUListElement>(null)
  const buscadorRef = useRef<HTMLInputElement>(null)

  const queryKey = ['proceso-matching', procesoId] as const
  const mutationKey = ['proceso-matching-decision', procesoId] as const
  const matchingQuery = useQuery({
    queryKey,
    queryFn: () => obtenerMatchingProceso(procesoId),
  })

  const decisionMutation = useMutation({
    mutationKey,
    mutationFn: ({ renglon, decision }: VariablesDecision) =>
      decision.tipo === 'confirmar'
        ? confirmarMatching(renglon.item_proceso_id, decision.producto.id)
        : marcarSinMatch(renglon.item_proceso_id),
    onMutate: async ({ renglon, decision }) => {
      await queryClient.cancelQueries({ queryKey })
      queryClient.setQueryData<MatchingProceso>(queryKey, (actual) =>
        reemplazarRenglon(actual, aplicarDecision(renglon, decision)),
      )
      return { previo: renglon }
    },
    onError: (_error, _variables, contexto) => {
      // Put back only this renglón: later decisions already applied stay.
      if (contexto) {
        queryClient.setQueryData<MatchingProceso>(queryKey, (actual) => reemplazarRenglon(actual, contexto.previo))
      }
    },
    onSettled: async () => {
      // Reload once the last pending decision ends, not after each one.
      if (queryClient.isMutating({ mutationKey }) <= 1) {
        await queryClient.invalidateQueries({ queryKey })
      }
    },
  })

  useEffect(() => {
    if (!avisoVisible) return
    const id = setTimeout(() => setAvisoVisible(false), DURACION_AVISO_MS)
    return () => clearTimeout(id)
  }, [avisoVisible, ultimo])

  const renglones = matchingQuery.data?.renglones ?? []
  const visibles = renglones.filter((r) => pasaFiltro(r, filtro))
  const seleccionado = visibles.find((r) => r.item_proceso_id === seleccionadoId) ?? visibles[0] ?? null
  const indice = seleccionado ? visibles.indexOf(seleccionado) : -1

  function seleccionar(itemProcesoId: string | null) {
    setSeleccionadoId(itemProcesoId)
    setTextoBusqueda('')
  }

  function mover(delta: number) {
    const destino = visibles[indice + delta]
    if (destino) seleccionar(destino.item_proceso_id)
  }

  function decidir(decision: Decision) {
    if (!seleccionado) return
    // The next renglón of the queue, taken before the decision changes it.
    const siguiente =
      visibles[indice + 1] ?? (filtro === 'abiertos' ? visibles[indice - 1] : seleccionado) ?? null
    decisionMutation.reset()
    decisionMutation.mutate({ renglon: seleccionado, decision })
    seleccionar(siguiente?.item_proceso_id ?? null)
    setUltimo({
      itemProcesoId: seleccionado.item_proceso_id,
      texto: `Renglón ${seleccionado.numero_renglon}: ${
        decision.tipo === 'confirmar' ? decision.producto.nombre : 'sin match'
      }`,
    })
    setAvisoVisible(true)
  }

  function volverAlUltimo() {
    if (!ultimo) return
    const renglon = renglones.find((r) => r.item_proceso_id === ultimo.itemProcesoId)
    if (!renglon) return
    if (!pasaFiltro(renglon, filtro)) setFiltro('todos')
    seleccionar(renglon.item_proceso_id)
    setAvisoVisible(false)
  }

  // Latest handlers for the document listeners, which are attached once.
  const teclado = useRef({ decidir, mover, volverAlUltimo, seleccionado })
  useLayoutEffect(() => {
    teclado.current = { decidir, mover, volverAlUltimo, seleccionado }
  })
  const shiftSolo = useRef(false)

  useEffect(() => {
    function alBajarTecla(event: KeyboardEvent) {
      shiftSolo.current = event.key === 'Shift' && !event.repeat
      if (esCampoDeTexto(event.target)) return
      const { decidir, mover, volverAlUltimo, seleccionado } = teclado.current

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        volverAlUltimo()
        return
      }
      if (event.ctrlKey || event.metaKey || event.altKey || !seleccionado) return

      // No shortcut uses a letter: typing a word always goes to the search (S11).
      if (event.key.length === 1 && /\p{L}/u.test(event.key)) {
        event.preventDefault()
        setTextoBusqueda((texto) => texto + event.key)
        buscadorRef.current?.focus()
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        mover(event.key === 'ArrowDown' ? 1 : -1)
      } else if (event.key === 'Enter') {
        // Enter on a focused button keeps activating that button.
        if (event.target instanceof HTMLElement && event.target.closest('button, a')) return
        const mejor = seleccionado.candidatos[0]
        if (mejor) {
          event.preventDefault()
          decidir({ tipo: 'confirmar', producto: mejor.producto })
        }
      } else if (/^[1-9]$/.test(event.key) && Number(event.key) <= CANDIDATOS_CON_TECLA) {
        const candidato = seleccionado.candidatos[Number(event.key) - 1]
        if (candidato) decidir({ tipo: 'confirmar', producto: candidato.producto })
      }
    }

    // Shift marks sin match on release and only when pressed alone, so capitals
    // (Shift+letter) and Shift+Tab never trigger it.
    function alSoltarTecla(event: KeyboardEvent) {
      if (event.key !== 'Shift') return
      const solo = shiftSolo.current
      shiftSolo.current = false
      if (!solo || esCampoDeTexto(event.target) || !teclado.current.seleccionado) return
      teclado.current.decidir({ tipo: 'sin_match' })
    }

    document.addEventListener('keydown', alBajarTecla)
    document.addEventListener('keyup', alSoltarTecla)
    return () => {
      document.removeEventListener('keydown', alBajarTecla)
      document.removeEventListener('keyup', alSoltarTecla)
    }
  }, [])

  if (matchingQuery.isPending) {
    return <div className="px-6 py-10 text-sm text-slate-500">Cargando matching…</div>
  }

  if (matchingQuery.isError || !matchingQuery.data) {
    return (
      <div className="px-6 py-10 text-sm text-red-600">
        {matchingQuery.error instanceof Error
          ? matchingQuery.error.message
          : 'No se pudo cargar el matching de este proceso.'}
      </div>
    )
  }

  const matching = matchingQuery.data
  const resueltos = renglones.filter(estaResuelto).length
  const avance = renglones.length ? (resueltos / renglones.length) * 100 : 0
  const errorDecision = decisionMutation.error

  return (
    <div className="flex h-svh flex-col bg-white">
      <header className="flex items-center gap-6 border-b border-slate-200 px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Matching de {matching.nombre}</h1>
          <p className="text-sm text-slate-600">
            {[
              matching.cliente,
              CLASE_LEGIBLE[matching.clase] ?? matching.clase,
              contar(renglones.length, 'renglón', 'renglones'),
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3 text-sm text-slate-600">
          <div
            role="progressbar"
            aria-label="Renglones resueltos"
            aria-valuemin={0}
            aria-valuemax={renglones.length}
            aria-valuenow={resueltos}
            className="h-2 w-50 overflow-hidden rounded-full bg-slate-100"
          >
            <div
              className="h-full bg-emerald-700 transition-[width] duration-200 motion-reduce:transition-none"
              style={{ width: `${avance}%` }}
            />
          </div>
          <span className="tabular-nums">
            {resueltos} de {renglones.length} resueltos
          </span>
        </div>
      </header>

      {errorDecision && (
        <p role="alert" className="mx-6 mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {errorDecision instanceof Error ? errorDecision.message : 'No se pudo guardar el matching.'}
        </p>
      )}

      <div className="flex min-h-0 flex-1">
        <section aria-label="Renglones" className="flex w-110 shrink-0 flex-col border-r border-slate-200">
          <div role="group" aria-label="Filtrar renglones" className="flex gap-1 border-b border-slate-200 px-4 py-3">
            {FILTROS.map(({ valor, etiqueta }) => (
              <button
                key={valor}
                type="button"
                aria-pressed={filtro === valor}
                onClick={() => {
                  setFiltro(valor)
                  seleccionar(null)
                }}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  filtro === valor
                    ? 'border-navy bg-navy text-white'
                    : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                {etiqueta}
              </button>
            ))}
          </div>
          <ColaRenglones
            renglones={visibles}
            seleccionadoId={seleccionado?.item_proceso_id ?? null}
            listaRef={listaRef}
            onSeleccionar={seleccionar}
          />
        </section>

        {seleccionado ? (
          <PanelRenglon
            renglon={seleccionado}
            total={renglones.length}
            textoBusqueda={textoBusqueda}
            onTextoBusqueda={setTextoBusqueda}
            buscadorRef={buscadorRef}
            onConfirmar={(producto) => decidir({ tipo: 'confirmar', producto })}
            onSinMatch={() => decidir({ tipo: 'sin_match' })}
            onSalirDelBuscador={() => listaRef.current?.focus()}
          />
        ) : (
          <p className="px-8 py-6 text-sm text-slate-500">
            {renglones.length === 0
              ? 'Este proceso no tiene renglones.'
              : filtro === 'abiertos'
                ? 'No quedan renglones por resolver.'
                : 'No hay renglones en este filtro.'}
          </p>
        )}
      </div>

      {ultimo && avisoVisible && (
        <div
          role="status"
          className="fixed right-6 bottom-6 flex items-center gap-3 rounded-md bg-navy px-4 py-2.5 text-sm text-white shadow-xl"
        >
          <span>{ultimo.texto}</span>
          <button
            type="button"
            onClick={volverAlUltimo}
            className="font-medium text-sky-200 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-200"
          >
            Volver (Ctrl+Z)
          </button>
        </div>
      )}
    </div>
  )
}
