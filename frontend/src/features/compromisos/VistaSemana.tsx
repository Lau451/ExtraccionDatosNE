import { Link } from '@tanstack/react-router'
import clsx from 'clsx'
import { useState } from 'react'
import type { EntregaCompromiso } from './agruparCompromisos'
import { diaSemanaLargo, fechaDiaMes, indiceDiaSemana } from './fechas'
import { contarEntregas, contarRenglones } from './textos'

const DIAS_CORTOS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']

function TarjetaSemana({ entrega }: { entrega: EntregaCompromiso }) {
  const [abierta, setAbierta] = useState(false)
  const vencida = entrega.situacion === 'vencida'
  const unidades = entrega.renglones.reduce((total, renglon) => total + renglon.cantidad_planificada, 0)
  return (
    <article
      className={clsx(
        'flex flex-col gap-1 rounded-md border-l-[3px] px-2.5 py-2',
        vencida ? 'border-red-300 bg-red-50' : 'border-sky-200 bg-sky-50',
        abierta && 'outline outline-1 outline-accent',
      )}
    >
      <button
        type="button"
        aria-expanded={abierta}
        onClick={() => setAbierta(!abierta)}
        className={clsx('text-left text-[13px] font-semibold hover:underline', vencida ? 'text-red-900' : 'text-sky-900')}
      >
        {entrega.cliente ?? 'Sin cliente'}
      </button>
      <p className="flex flex-wrap items-center gap-x-1.5 text-[11px] text-slate-600">
        <Link
          to="/ordenes-compra/$ordenCompraId"
          params={{ ordenCompraId: entrega.orden_compra_id }}
          className="text-xs font-medium text-accent underline"
        >
          OC {entrega.numero_oc}
        </Link>
        <span>
          Entrega {entrega.posicion_en_plan} de {entrega.entregas_en_plan}
        </span>
      </p>
      <p className="text-[11px] text-slate-600">
        {contarRenglones(entrega.renglones.length)} · {unidades.toLocaleString('es-AR')} u.
      </p>
      {abierta ? (
        <ul className="mt-1 flex flex-col gap-1 border-t border-sky-200 pt-1.5">
          {entrega.renglones.map((renglon, indice) => (
            <li key={`${renglon.numero_renglon ?? 'x'}-${indice}`} className="flex justify-between gap-1.5 text-[11px]">
              <span className="text-slate-700">{renglon.descripcion ?? renglon.codigo_articulo ?? 'Sin descripción'}</span>
              <span className="font-medium tabular-nums text-slate-900">
                {renglon.cantidad_planificada.toLocaleString('es-AR')}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  )
}

interface VistaSemanaProps {
  dias: string[]
  hoy: string
  porFecha: Map<string, EntregaCompromiso[]>
  cargando?: boolean
}

/** Una columna por día (fin de semana más angosto) con las entregas como tarjetas. */
export function VistaSemana({ dias, hoy, porFecha, cargando = false }: VistaSemanaProps) {
  return (
    <div
      aria-busy={cargando}
      className="flex min-w-0 flex-1 overflow-hidden rounded-lg border border-slate-200 bg-white"
    >
      {cargando ? (
        <p role="status" className="sr-only">
          Cargando compromisos…
        </p>
      ) : null}
      {dias.map((fecha) => {
        const entregas = porFecha.get(fecha) ?? []
        const finDeSemana = indiceDiaSemana(fecha) >= 5
        const esHoy = fecha === hoy
        return (
          <section
            key={fecha}
            aria-label={`${diaSemanaLargo(fecha)} ${fechaDiaMes(fecha)}`}
            aria-current={esHoy ? 'date' : undefined}
            className={clsx(
              'flex flex-col border-r border-slate-200 last:border-r-0',
              finDeSemana ? 'w-24 shrink-0 bg-slate-50/40' : 'min-w-0 flex-1',
            )}
          >
            <header className="flex flex-col gap-0.5 border-b border-slate-200 p-3">
              <span className="text-[11px] font-semibold tracking-wide text-slate-400">
                {DIAS_CORTOS[indiceDiaSemana(fecha)]}
              </span>
              <span className="flex items-center justify-between gap-1">
                <span
                  className={clsx(
                    'text-xl font-semibold tabular-nums',
                    esHoy ? 'text-accent' : finDeSemana ? 'text-slate-400' : 'text-slate-900',
                  )}
                >
                  {Number(fecha.slice(8, 10))}
                </span>
                {entregas.length > 0 ? (
                  <span className="text-[11px] text-slate-600">{contarEntregas(entregas.length)}</span>
                ) : null}
              </span>
            </header>
            <div className="flex flex-1 flex-col gap-2 p-2">
              {cargando ? (
                <span aria-hidden="true" className="h-16 animate-pulse rounded-md bg-slate-100" />
              ) : entregas.length > 0 ? (
                entregas.map((entrega) => <TarjetaSemana key={entrega.entrega_oc_id} entrega={entrega} />)
              ) : finDeSemana ? null : (
                <p className="text-xs text-slate-400">Sin entregas</p>
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
