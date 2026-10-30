import { useEffect, useState, type Ref } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ProductoResumen } from '@/lib/api/matching'
import { listarProductos } from '@/lib/api/productos'

const DEBOUNCE_BUSQUEDA_MS = 300
const Q_MINIMO = 2
const RESULTADOS_MAXIMOS = 10

interface Props {
  texto: string
  onTexto: (texto: string) => void
  inputRef: Ref<HTMLInputElement>
  onElegir: (producto: ProductoResumen) => void
  /** Tab leaves the search and goes back to the renglones (S11). */
  onSalir: () => void
}

/** Catalog search for a renglón none of whose candidatos fits (S10). Searches
 * the server (`GET /productos?q=`, by nombre or código) instead of loading the
 * whole catalog; needs at least 2 characters. The text is owned by the screen,
 * which starts it with the letter typed anywhere on it (S11). Enter confirms
 * the first result. */
export function ProductoBuscador({ texto, onTexto, inputRef, onElegir, onSalir }: Props) {
  const [textoDebounced, setTextoDebounced] = useState(texto.trim())

  useEffect(() => {
    const id = setTimeout(() => setTextoDebounced(texto.trim()), DEBOUNCE_BUSQUEDA_MS)
    return () => clearTimeout(id)
  }, [texto])

  const habilitada = textoDebounced.length >= Q_MINIMO

  const { data, isPending } = useQuery({
    queryKey: ['proceso-matching-productos', textoDebounced],
    queryFn: () => listarProductos({ q: textoDebounced, pageSize: RESULTADOS_MAXIMOS }),
    enabled: habilitada,
  })

  const resultados: ProductoResumen[] = habilitada
    ? (data?.items ?? []).map((producto) => ({
        id: producto.id,
        nombre: producto.nombre,
        codigo_interno: producto.codigo_interno,
      }))
    : []

  function alPresionarTecla(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault()
      onSalir()
    } else if (event.key === 'Enter' && resultados[0]) {
      event.preventDefault()
      onElegir(resultados[0])
    }
  }

  return (
    <div className="space-y-2">
      <label
        htmlFor="matching-buscador"
        className="text-xs font-medium uppercase tracking-wide text-slate-500"
      >
        Otro producto · empezá a escribir
      </label>
      <input
        id="matching-buscador"
        ref={inputRef}
        type="text"
        value={texto}
        onChange={(event) => onTexto(event.target.value)}
        onKeyDown={alPresionarTecla}
        aria-label="Buscar otro producto en el catálogo"
        placeholder="Buscá en el catálogo por nombre o código"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      />

      {habilitada && isPending && <p className="text-sm text-slate-500">Buscando…</p>}

      {habilitada && !isPending && resultados.length === 0 && (
        <p className="text-sm text-slate-500">Sin resultados para “{textoDebounced}”.</p>
      )}

      {resultados.length > 0 && (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
          {resultados.map((producto, indice) => (
            <li key={producto.id}>
              <button
                type="button"
                aria-label={`Confirmar ${producto.nombre} (${producto.codigo_interno})`}
                onClick={() => onElegir(producto)}
                className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
              >
                <span>
                  <span className="font-medium text-slate-900">{producto.nombre}</span>
                  <span className="ml-2 font-mono text-xs text-slate-500">{producto.codigo_interno}</span>
                </span>
                {indice === 0 && <span className="text-xs text-slate-500">Enter confirma</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
