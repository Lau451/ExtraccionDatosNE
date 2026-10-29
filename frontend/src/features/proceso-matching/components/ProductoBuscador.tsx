import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ProductoResumen } from '@/lib/api/matching'
import { listarProductos } from '@/lib/api/productos'

const DEBOUNCE_BUSQUEDA_MS = 300
const Q_MINIMO = 2
const RESULTADOS_MAXIMOS = 10

interface Props {
  disabled: boolean
  onElegir: (producto: ProductoResumen) => void
}

/** Catalog search for a renglón none of whose candidatos fits (S10). Searches
 * the server (`GET /productos?q=`, by nombre or código) instead of loading the
 * whole catalog; starts empty and needs at least 2 characters. */
export function ProductoBuscador({ disabled, onElegir }: Props) {
  const [texto, setTexto] = useState('')
  const [textoDebounced, setTextoDebounced] = useState('')

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

  const resultados = data?.items ?? []

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={texto}
        onChange={(event) => setTexto(event.target.value)}
        placeholder="Buscá en el catálogo por nombre o código"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />

      {habilitada && isPending && <p className="text-sm text-slate-500">Buscando…</p>}

      {habilitada && !isPending && resultados.length === 0 && (
        <p className="text-sm text-slate-500">Sin resultados para “{textoDebounced}”.</p>
      )}

      {resultados.length > 0 && (
        <ul className="divide-y divide-slate-200 rounded-md border border-slate-200 bg-white">
          {resultados.map((producto) => (
            <li key={producto.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span>
                <span className="font-medium text-slate-900">{producto.nombre}</span>
                <span className="ml-2 text-slate-500">{producto.codigo_interno}</span>
              </span>
              <button
                type="button"
                disabled={disabled}
                aria-label={`Confirmar ${producto.nombre} (${producto.codigo_interno})`}
                onClick={() =>
                  onElegir({
                    id: producto.id,
                    nombre: producto.nombre,
                    codigo_interno: producto.codigo_interno,
                  })
                }
                className="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                Confirmar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
