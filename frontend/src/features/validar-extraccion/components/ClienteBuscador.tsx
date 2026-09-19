import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listarTerceros, type Tercero } from '@/lib/api/terceros'

const DEBOUNCE_BUSQUEDA_MS = 300
const Q_MINIMO = 2

interface Props {
  onSeleccionar: (tercero: Tercero) => void
}

/** Nivel 3 de D3 (y "rechazar la sugerencia" de los niveles 1 y 2): búsqueda
 * manual sobre `GET /terceros`, ya existente (D3.2). Dos ajustes obligados por
 * C7: `rol: 'todos'` (nunca `'clientes'`, que ocultaría un tercero con doble
 * rol -- C7-iii) con filtrado client-side por `tiene_rol_cliente`, y `q`
 * obligatorio con mínimo 2 caracteres + debounce de 300ms para no barrer las
 * 5541 filas de la droguería en cada apertura (C7-ii: la paginación de ese
 * endpoint no baja a la base). Arranca vacío, nunca lista sin `q`. */
export function ClienteBuscador({ onSeleccionar }: Props) {
  const [texto, setTexto] = useState('')
  const [textoDebounced, setTextoDebounced] = useState('')

  useEffect(() => {
    const id = setTimeout(() => setTextoDebounced(texto.trim()), DEBOUNCE_BUSQUEDA_MS)
    return () => clearTimeout(id)
  }, [texto])

  const habilitada = textoDebounced.length >= Q_MINIMO

  const { data, isPending } = useQuery({
    queryKey: ['terceros-cliente-buscador', textoDebounced],
    queryFn: () => listarTerceros({ q: textoDebounced, rol: 'todos', pageSize: 20 }),
    enabled: habilitada,
  })

  // C7-iii: rol='todos' trae también proveedores; el picker de OC solo
  // muestra los que además son clientes.
  const resultados = (data?.items ?? []).filter((tercero) => tercero.tiene_rol_cliente === true)

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={texto}
        onChange={(event) => setTexto(event.target.value)}
        placeholder="Buscá por razón social, CUIT o código"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />

      {habilitada && isPending && <p className="text-sm text-slate-500">Buscando…</p>}

      {habilitada && !isPending && resultados.length === 0 && (
        <p className="text-sm text-slate-500">Sin resultados para “{textoDebounced}”.</p>
      )}

      {resultados.length > 0 && (
        <ul className="divide-y divide-slate-200 rounded-md border border-slate-200">
          {resultados.map((tercero) => (
            <li key={tercero.id}>
              <button
                type="button"
                onClick={() => onSeleccionar(tercero)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-medium text-slate-900">{tercero.razon_social}</span>
                <span className="ml-2 text-slate-500">
                  CUIT {tercero.cuit ?? 'sin CUIT'} · {tercero.codigo_interno ?? 'sin código'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
