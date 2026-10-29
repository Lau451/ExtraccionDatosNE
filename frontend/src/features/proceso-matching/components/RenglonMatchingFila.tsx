import type { CandidatoRenglon, EstadoMatching, RenglonMatching } from '@/lib/api/matching'
import { ProductoBuscador } from './ProductoBuscador'

const ESTADOS_RESUELTOS: EstadoMatching[] = ['automatico', 'confirmado', 'sin_match']

const ESTILO_ESTADO: Record<EstadoMatching, string> = {
  pendiente: 'bg-amber-50 text-amber-800 ring-amber-200',
  sugerido: 'bg-sky-50 text-sky-800 ring-sky-200',
  automatico: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  confirmado: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  sin_match: 'bg-slate-100 text-slate-700 ring-slate-200',
}

function estaResuelto(renglon: RenglonMatching): boolean {
  return ESTADOS_RESUELTOS.includes(renglon.estado_matching)
}

function porcentaje(confianza: string): string {
  return `${Math.round(Number(confianza))}%`
}

function etiquetaEstado(renglon: RenglonMatching): string {
  switch (renglon.estado_matching) {
    case 'pendiente':
      return 'Pendiente'
    case 'sugerido':
      return renglon.confianza_matching ? `Sugerido ${porcentaje(renglon.confianza_matching)}` : 'Sugerido'
    case 'automatico':
      return 'Automático'
    case 'confirmado':
      return 'Confirmado'
    case 'sin_match':
      return 'Sin match'
  }
}

function formatearCantidad(cantidad: string): string {
  return Number(cantidad).toLocaleString('es-AR', { maximumFractionDigits: 2 })
}

interface Props {
  renglon: RenglonMatching
  abierto: boolean
  isPending: boolean
  onAlternar: () => void
  onConfirmar: (productoId: string) => void
  onSinMatch: () => void
}

/** One renglón of the matching screen plus, when open, the panel to decide it:
 * its candidatos (best first), the catalog search and "sin match". Resolved
 * renglones (automatico, confirmado, sin match) can be changed too (S10). */
export function RenglonMatchingFila({
  renglon,
  abierto,
  isPending,
  onAlternar,
  onConfirmar,
  onSinMatch,
}: Props) {
  const mejorCandidato: CandidatoRenglon | undefined = renglon.candidatos[0]
  const resuelto = estaResuelto(renglon)

  return (
    <>
      <tr aria-label={`Renglón ${renglon.numero_renglon}`} className="align-top">
        <td className="py-3 pr-4 text-sm tabular-nums text-slate-500">{renglon.numero_renglon}</td>
        <td className="py-3 pr-4 text-sm text-slate-900">{renglon.descripcion}</td>
        <td className="py-3 pr-4 text-right text-sm tabular-nums text-slate-700">
          {formatearCantidad(renglon.cantidad)}
        </td>
        <td className="whitespace-nowrap py-3 pr-4">
          <span
            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${ESTILO_ESTADO[renglon.estado_matching]}`}
          >
            {etiquetaEstado(renglon)}
          </span>
        </td>
        <td className="py-3 pr-4 text-sm">
          {renglon.producto ? (
            <span className="text-slate-900">{renglon.producto.nombre}</span>
          ) : renglon.estado_matching === 'sin_match' ? (
            <span className="text-slate-500">Sin producto</span>
          ) : mejorCandidato ? (
            <span className="italic text-slate-600">{mejorCandidato.producto.nombre}</span>
          ) : (
            <span className="text-slate-500">Sin candidatos</span>
          )}
        </td>
        <td className="whitespace-nowrap py-3 text-right">
          <div className="flex justify-end gap-2">
            {renglon.estado_matching === 'sugerido' && mejorCandidato && (
              <button
                type="button"
                disabled={isPending}
                onClick={() => onConfirmar(mejorCandidato.producto.id)}
                className="rounded-md bg-navy px-2.5 py-1 text-xs font-medium text-white disabled:opacity-40"
              >
                Confirmar sugerencia
              </button>
            )}
            <button
              type="button"
              aria-expanded={abierto}
              onClick={onAlternar}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              {resuelto ? 'Cambiar' : 'Elegir'}
            </button>
          </div>
        </td>
      </tr>

      {abierto && (
        <tr>
          <td colSpan={6} className="pb-4">
            <section
              aria-label={`Elegir producto para el renglón ${renglon.numero_renglon}`}
              className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-4"
            >
              {renglon.candidatos.length > 0 ? (
                <ul className="divide-y divide-slate-200 rounded-md border border-slate-200 bg-white">
                  {renglon.candidatos.map((candidato) => (
                    <li
                      key={candidato.producto.id}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                    >
                      <span>
                        <span className="font-medium text-slate-900">{candidato.producto.nombre}</span>
                        <span className="ml-2 text-slate-500">{candidato.producto.codigo_interno}</span>
                        <span className="ml-2 tabular-nums text-slate-500">{porcentaje(candidato.confianza)}</span>
                        {candidato.elegido && (
                          <span className="ml-2 text-xs font-medium text-emerald-700">Elegido</span>
                        )}
                      </span>
                      <button
                        type="button"
                        disabled={isPending}
                        aria-label={`Confirmar ${candidato.producto.nombre} (${candidato.producto.codigo_interno}) ${porcentaje(candidato.confianza)}`}
                        onClick={() => onConfirmar(candidato.producto.id)}
                        className="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                      >
                        Confirmar
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">El matching no encontró candidatos para este renglón.</p>
              )}

              <ProductoBuscador disabled={isPending} onElegir={(producto) => onConfirmar(producto.id)} />

              {renglon.estado_matching !== 'sin_match' && (
                <button
                  type="button"
                  disabled={isPending}
                  onClick={onSinMatch}
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Marcar sin match
                </button>
              )}
            </section>
          </td>
        </tr>
      )}
    </>
  )
}
