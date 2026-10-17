import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { listarCompromisos } from '@/lib/api/compromisos'
import { agruparEntregas, entregasPorFecha, filtrarEntregas } from './agruparCompromisos'
import { etiquetaMes, hoyBuenosAires, mesDe, nombreMes, semanasDelMes, sumarDias, sumarMeses } from './fechas'
import { VistaLista } from './VistaLista'
import { contarEntregas } from './textos'
import { VistaMes } from './VistaMes'

type Vista = 'mes' | 'lista'

const VISTAS: { valor: Vista; etiqueta: string }[] = [
  { valor: 'mes', etiqueta: 'Mes' },
  { valor: 'lista', etiqueta: 'Lista' },
]

function Chevron({ direccion }: { direccion: 'izquierda' | 'derecha' }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="size-4">
      <path
        d={direccion === 'izquierda' ? 'M10 3.5 5.5 8l4.5 4.5' : 'M6 3.5 10.5 8 6 12.5'}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Contador({ tono, children }: { tono: 'vencida' | 'periodo'; children: React.ReactNode }) {
  return (
    <span
      className={clsx(
        'flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-medium',
        tono === 'vencida' ? 'bg-red-50 text-red-800' : 'bg-sky-50 text-sky-800',
      )}
    >
      <span aria-hidden="true" className={clsx('size-2 rounded-full', tono === 'vencida' ? 'bg-red-700' : 'bg-accent')} />
      {children}
    </span>
  )
}

/** /compromisos: agenda de entregas comprometidas en calendario (Mes) o como lista. */
export function Compromisos() {
  const hoy = useMemo(() => hoyBuenosAires(), [])
  const [vista, setVista] = useState<Vista>('mes')
  const [mes, setMes] = useState(() => mesDe(hoy))
  const [seleccion, setSeleccion] = useState(hoy)
  const [busqueda, setBusqueda] = useState('')

  const semanas = semanasDelMes(mes)
  const rango = { desde: semanas[0][0], hasta: semanas[semanas.length - 1][6] }
  const ayer = sumarDias(hoy, -1)

  const periodo = useQuery({
    queryKey: ['compromisos-entregas', rango.desde, rango.hasta],
    queryFn: () => listarCompromisos(rango),
    enabled: vista !== 'lista',
  })
  const vencidas = useQuery({
    queryKey: ['compromisos-entregas', 'vencidas', ayer],
    queryFn: () => listarCompromisos({ hasta: ayer }),
  })

  const entregas = filtrarEntregas(agruparEntregas(periodo.data ?? []), busqueda)
  const porFecha = entregasPorFecha(entregas)
  const delMes = entregas.filter((e) => e.fecha_entrega_planificada && mesDe(e.fecha_entrega_planificada) === mes)
  const cantidadVencidas = filtrarEntregas(agruparEntregas(vencidas.data ?? []), busqueda).length

  function irAMes(destino: string, fecha: string) {
    setMes(destino)
    setSeleccion(fecha)
  }

  return (
    <div className="flex min-h-full flex-col gap-5 p-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Compromisos de entrega</h1>
          <p className="mt-1 text-sm text-slate-600">Entregas planificadas de OC exportadas a Progress</p>
        </div>
        <div className="flex gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-[3px]">
          {VISTAS.map(({ valor, etiqueta }) => (
            <button
              key={valor}
              type="button"
              aria-pressed={vista === valor}
              onClick={() => setVista(valor)}
              className={clsx(
                'rounded-md px-3 py-1.5 text-[13px]',
                vista === valor ? 'bg-white font-medium text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900',
              )}
            >
              {etiqueta}
            </button>
          ))}
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        {vista === 'mes' ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Mes anterior"
              onClick={() => irAMes(sumarMeses(mes, -1), `${sumarMeses(mes, -1)}-01`)}
              className="flex size-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            >
              <Chevron direccion="izquierda" />
            </button>
            <button
              type="button"
              aria-label="Mes siguiente"
              onClick={() => irAMes(sumarMeses(mes, 1), `${sumarMeses(mes, 1)}-01`)}
              className="flex size-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            >
              <Chevron direccion="derecha" />
            </button>
            <h2 className="min-w-36 text-lg font-semibold text-slate-900">{etiquetaMes(mes)}</h2>
            <button
              type="button"
              onClick={() => irAMes(mesDe(hoy), hoy)}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 hover:bg-slate-50"
            >
              Hoy
            </button>
          </div>
        ) : (
          <span />
        )}
        <div className="flex flex-wrap items-center gap-3">
          {cantidadVencidas > 0 ? (
            <Contador tono="vencida">
              {cantidadVencidas} {cantidadVencidas === 1 ? 'vencida' : 'vencidas'} sin confirmar
            </Contador>
          ) : null}
          {vista === 'mes' && periodo.isSuccess ? (
            <Contador tono="periodo">
              {contarEntregas(delMes.length)} en {nombreMes(mes)}
            </Contador>
          ) : null}
          <input
            type="search"
            value={busqueda}
            onChange={(evento) => setBusqueda(evento.target.value)}
            placeholder="Buscar cliente u OC"
            aria-label="Buscar cliente u OC"
            className="w-60 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      {vista === 'lista' ? (
        <VistaLista filtro={busqueda} />
      ) : (
        <div className="flex flex-1 gap-5">
          <VistaMes mes={mes} hoy={hoy} seleccion={seleccion} porFecha={porFecha} onSeleccionar={setSeleccion} />
        </div>
      )}
    </div>
  )
}
