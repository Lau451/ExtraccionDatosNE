import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import type { EntregaCompromiso } from './agruparCompromisos'
import { diaSemanaLargo, fechaCorta, fechaDiaMes } from './fechas'
import { contarEntregas, contarRenglones } from './textos'

const VENCIDAS_VISIBLES = 3
const RENGLONES_VISIBLES = 3

interface PanelVencidasProps {
  vencidas: EntregaCompromiso[]
  onVerTodas: () => void
}

/** Las vencidas más viejas primero; el total completo se ve en la Lista. */
export function PanelVencidas({ vencidas, onVerTodas }: PanelVencidasProps) {
  const masViejas = [...vencidas].sort((a, b) =>
    (a.fecha_entrega_planificada ?? '').localeCompare(b.fecha_entrega_planificada ?? ''),
  )
  return (
    <section aria-label="Vencidas sin confirmar" className="flex flex-col gap-2.5 rounded-lg border border-red-200 bg-red-50 p-4">
      <div className="flex items-center gap-2">
        <h2 className="flex-1 text-sm font-semibold text-red-800">Vencidas sin confirmar</h2>
        <span className="text-[13px] font-semibold tabular-nums text-red-800">{vencidas.length}</span>
      </div>
      <ul className="flex flex-col gap-2">
        {masViejas.slice(0, VENCIDAS_VISIBLES).map((entrega) => (
          <li key={entrega.entrega_oc_id} className="flex items-center gap-2 text-xs">
            <Link
              to="/ordenes-compra/$ordenCompraId"
              params={{ ordenCompraId: entrega.orden_compra_id }}
              className="font-semibold text-accent underline"
            >
              {entrega.numero_oc}
            </Link>
            <span className="min-w-0 flex-1 truncate text-slate-900">{entrega.cliente ?? 'Sin cliente'}</span>
            <span className="whitespace-nowrap text-red-700">
              {entrega.fecha_entrega_planificada ? fechaCorta(entrega.fecha_entrega_planificada) : 'Sin fecha'} ·{' '}
              {entrega.dias_atraso} {entrega.dias_atraso === 1 ? 'día' : 'días'}
            </span>
          </li>
        ))}
      </ul>
      {vencidas.length > VENCIDAS_VISIBLES ? (
        <button type="button" onClick={onVerTodas} className="self-start text-xs font-medium text-red-800 hover:underline">
          Ver las {vencidas.length} vencidas →
        </button>
      ) : null}
    </section>
  )
}

function EntregaDelDia({ entrega }: { entrega: EntregaCompromiso }) {
  const [abierta, setAbierta] = useState(false)
  const ocultos = entrega.renglones.length - RENGLONES_VISIBLES
  const visibles = abierta ? entrega.renglones : entrega.renglones.slice(0, RENGLONES_VISIBLES)
  return (
    <article className="flex flex-col gap-1.5 border-b border-slate-200 px-4 py-3 last:border-b-0">
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 truncate text-[13px] font-semibold text-slate-900">
          {entrega.cliente ?? 'Sin cliente'}
        </h3>
        <Link
          to="/ordenes-compra/$ordenCompraId"
          params={{ ordenCompraId: entrega.orden_compra_id }}
          className="whitespace-nowrap text-xs font-medium text-accent underline"
        >
          OC {entrega.numero_oc}
        </Link>
      </div>
      <p className="text-[11px] text-slate-600">
        Entrega {entrega.posicion_en_plan} de {entrega.entregas_en_plan}
        {entrega.situacion === 'vencida' ? <span className="text-red-700"> · vencida</span> : null}
      </p>
      <ul className="flex flex-col gap-1">
        {visibles.map((renglon, indice) => (
          <li key={`${renglon.numero_renglon ?? 'x'}-${indice}`} className="flex justify-between gap-3 text-xs">
            <span className="text-slate-700">{renglon.descripcion ?? renglon.codigo_articulo ?? 'Sin descripción'}</span>
            <span className="font-medium tabular-nums text-slate-900">
              {renglon.cantidad_planificada.toLocaleString('es-AR')}
            </span>
          </li>
        ))}
      </ul>
      {ocultos > 0 && !abierta ? (
        <button
          type="button"
          onClick={() => setAbierta(true)}
          className="self-start text-[11px] text-slate-500 hover:text-slate-900"
        >
          +{contarRenglones(ocultos)}
        </button>
      ) : null}
    </article>
  )
}

/** Detalle del día elegido en la grilla: cada entrega con su lugar en el plan y sus renglones. */
export function DetalleDia({ fecha, entregas }: { fecha: string; entregas: EntregaCompromiso[] }) {
  const renglones = entregas.reduce((total, entrega) => total + entrega.renglones.length, 0)
  return (
    <section
      aria-label="Detalle del día"
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white"
    >
      <header className="flex flex-col gap-0.5 border-b border-slate-200 px-4 py-3.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{diaSemanaLargo(fecha)}</p>
        <h2 className="text-lg font-semibold text-slate-900">{fechaDiaMes(fecha)}</h2>
        {entregas.length > 0 ? (
          <p className="text-xs text-slate-600">
            {contarEntregas(entregas.length)} · {contarRenglones(renglones)}
          </p>
        ) : null}
      </header>
      {entregas.length > 0 ? (
        <div className="overflow-y-auto">
          {entregas.map((entrega) => (
            <EntregaDelDia key={entrega.entrega_oc_id} entrega={entrega} />
          ))}
        </div>
      ) : (
        <p className="px-4 py-3 text-sm text-slate-500">Sin entregas este día</p>
      )}
    </section>
  )
}
