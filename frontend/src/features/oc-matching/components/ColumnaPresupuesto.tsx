import { useMemo, useState } from 'react'
import type { RenglonOrdenCompra, RenglonPresupuesto } from '@/lib/api/ocMatching'
import { AvisoReutilizacion } from './AvisoReutilizacion'

interface Props {
  renglones: RenglonPresupuesto[]
  /** Renglón de OC actualmente resaltado en la columna derecha (D12, único
   * estado local del container): permite marcar del lado del presupuesto qué
   * filas son candidatas de ese renglón de OC. */
  renglonOcSeleccionado: RenglonOrdenCompra | null
}

/** Quita diacríticos y normaliza mayúsculas para comparar texto de forma
 * tolerante a acentos (spec T2: "un presupuesto de 300 líneas se puede
 * acotar tipeando"). */
function normalizarTexto(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

/** Coincide si el término de búsqueda aparece en la descripción (sin acentos
 * ni mayúsculas) o si es exactamente el número de renglón. */
function coincideBusqueda(renglon: RenglonPresupuesto, busqueda: string): boolean {
  const termino = busqueda.trim()
  if (!termino) return true
  if (normalizarTexto(renglon.descripcion).includes(normalizarTexto(termino))) return true
  const numero = Number(termino)
  return !Number.isNaN(numero) && renglon.numero_renglon === numero
}

/** Columna izquierda de la pantalla de matching (design.md § Forma del
 * frontend): descripción/cantidad/precio/estado por `RenglonPresupuesto`,
 * integrando el aviso de reutilización N:1 por fila (D5), con búsqueda y
 * filtro de candidatos para presupuestos largos (T2). */
export function ColumnaPresupuesto({ renglones, renglonOcSeleccionado }: Props) {
  const [busqueda, setBusqueda] = useState('')
  const [soloCandidatos, setSoloCandidatos] = useState(false)
  const haySeleccion = renglonOcSeleccionado !== null

  const idsCandidatos = new Set(
    renglonOcSeleccionado?.candidatos.map((candidato) => candidato.presupuesto_item_id) ?? [],
  )

  const renglonesFiltrados = useMemo(
    () =>
      renglones.filter((renglon) => {
        if (soloCandidatos && haySeleccion && !idsCandidatos.has(renglon.presupuesto_item_id)) {
          return false
        }
        return coincideBusqueda(renglon, busqueda)
      }),
    // idsCandidatos se recalcula cada render a partir de renglonOcSeleccionado,
    // que es la dependencia real de la que depende su contenido.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [renglones, busqueda, soloCandidatos, haySeleccion, renglonOcSeleccionado],
  )

  return (
    <section aria-label="Renglones del presupuesto" className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-700">Presupuesto</h2>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          aria-label="Buscar en el presupuesto"
          placeholder="Buscar por descripción o número de renglón"
          value={busqueda}
          onChange={(evento) => setBusqueda(evento.target.value)}
          className="min-w-[220px] flex-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
        <label className="flex items-center gap-1 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={soloCandidatos}
            disabled={!haySeleccion}
            onChange={(evento) => setSoloCandidatos(evento.target.checked)}
          />
          Solo candidatos
        </label>
      </div>

      <div role="list" className="space-y-2">
        {renglonesFiltrados.length === 0 && (
          <p className="text-sm text-slate-500">Ningún renglón del presupuesto coincide con la búsqueda.</p>
        )}
        {renglonesFiltrados.map((renglon) => (
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
