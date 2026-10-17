import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { listarCompromisos, obtenerProximaFecha } from '@/lib/api/compromisos'
import { ApiError } from '@/lib/api/presupuestacion'
import { agruparEntregas, entregasPorFecha, filtrarEntregas } from './agruparCompromisos'
import {
  diasDeSemana,
  etiquetaMes,
  etiquetaSemana,
  fechaDiaMes,
  hoyBuenosAires,
  inicioSemana,
  mesDe,
  nombreMes,
  semanasDelMes,
  sumarDias,
  sumarMeses,
} from './fechas'
import { DetalleDia, PanelVencidas } from './PanelLateral'
import { Superposicion } from './Superposicion'
import { contarEntregas } from './textos'
import { VistaLista } from './VistaLista'
import { VistaMes } from './VistaMes'
import { VistaSemana } from './VistaSemana'

type Vista = 'mes' | 'semana' | 'lista'

const VISTAS: { valor: Vista; etiqueta: string }[] = [
  { valor: 'mes', etiqueta: 'Mes' },
  { valor: 'semana', etiqueta: 'Semana' },
  { valor: 'lista', etiqueta: 'Lista' },
]

const BOTON_ICONO =
  'flex size-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'

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

/** /compromisos: entregas comprometidas en calendario (Mes, Semana) o como lista.
 * El día elegido es la única fuente de verdad del período: el mes y la semana
 * visibles son los que lo contienen. */
export function Compromisos() {
  const hoy = useMemo(() => hoyBuenosAires(), [])
  const [vista, setVista] = useState<Vista>('mes')
  const [seleccion, setSeleccion] = useState(hoy)
  const [busqueda, setBusqueda] = useState('')

  const mes = mesDe(seleccion)
  const inicio = inicioSemana(seleccion)
  const semanas = semanasDelMes(mes)
  const rango =
    vista === 'semana'
      ? { desde: inicio, hasta: sumarDias(inicio, 6) }
      : { desde: semanas[0][0], hasta: semanas[semanas.length - 1][6] }
  const finDelPeriodo = vista === 'semana' ? rango.hasta : sumarDias(`${sumarMeses(mes, 1)}-01`, -1)
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

  // En Mes la grilla incluye días de los meses vecinos: los contadores y el
  // estado vacío miran solo el mes.
  const enPeriodo = (e: { fecha_entrega_planificada: string | null }) =>
    e.fecha_entrega_planificada !== null && (vista === 'semana' || mesDe(e.fecha_entrega_planificada) === mes)
  const todas = agruparEntregas(periodo.data ?? [])
  const entregas = filtrarEntregas(todas, busqueda)
  const porFecha = entregasPorFecha(entregas)
  const delPeriodo = entregas.filter(enPeriodo)
  const periodoVacio = periodo.isSuccess && !todas.some(enPeriodo)
  const sinCoincidencias = periodo.isSuccess && !periodoVacio && delPeriodo.length === 0
  const listaVencidas = filtrarEntregas(agruparEntregas(vencidas.data ?? []), busqueda)

  const proxima = useQuery({
    queryKey: ['compromisos-entregas', 'proxima', finDelPeriodo],
    queryFn: () => obtenerProximaFecha(finDelPeriodo),
    enabled: vista !== 'lista' && periodoVacio,
  })

  const nombrePeriodo = vista === 'semana' ? 'esta semana' : `en ${nombreMes(mes)}`
  const paso = vista === 'semana' ? 'Semana' : 'Mes'

  function moverPeriodo(sentido: 1 | -1) {
    setSeleccion(vista === 'semana' ? sumarDias(seleccion, 7 * sentido) : `${sumarMeses(mes, sentido)}-01`)
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
        {vista !== 'lista' ? (
          <div className="flex items-center gap-2">
            <button type="button" aria-label={`${paso} anterior`} onClick={() => moverPeriodo(-1)} className={BOTON_ICONO}>
              <Chevron direccion="izquierda" />
            </button>
            <button type="button" aria-label={`${paso} siguiente`} onClick={() => moverPeriodo(1)} className={BOTON_ICONO}>
              <Chevron direccion="derecha" />
            </button>
            <h2 className="min-w-36 text-lg font-semibold text-slate-900">
              {vista === 'semana' ? etiquetaSemana(inicio) : etiquetaMes(mes)}
            </h2>
            <button
              type="button"
              onClick={() => setSeleccion(hoy)}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 hover:bg-slate-50"
            >
              Hoy
            </button>
          </div>
        ) : (
          <span />
        )}
        <div className="flex flex-wrap items-center gap-3">
          {listaVencidas.length > 0 ? (
            <Contador tono="vencida">
              {listaVencidas.length} {listaVencidas.length === 1 ? 'vencida' : 'vencidas'} sin confirmar
            </Contador>
          ) : null}
          {vista !== 'lista' && periodo.isSuccess ? (
            <Contador tono="periodo">
              {contarEntregas(delPeriodo.length)} {nombrePeriodo}
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
          <div className="relative flex min-w-0 flex-1">
            {vista === 'semana' ? (
              <VistaSemana dias={diasDeSemana(inicio)} hoy={hoy} porFecha={porFecha} cargando={periodo.isPending} />
            ) : (
              <VistaMes
                mes={mes}
                hoy={hoy}
                seleccion={seleccion}
                porFecha={porFecha}
                cargando={periodo.isPending}
                onSeleccionar={setSeleccion}
              />
            )}
            {periodo.isError ? (
              <Superposicion
                tono="error"
                titulo="No se pudieron cargar los compromisos"
                descripcion={
                  periodo.error instanceof ApiError
                    ? periodo.error.message
                    : 'Revisá tu conexión e intentá de nuevo. Si sigue fallando, avisá a Sistemas.'
                }
                accion={{ etiqueta: 'Reintentar', onClick: () => void periodo.refetch() }}
              />
            ) : periodoVacio ? (
              <Superposicion
                tono="info"
                titulo={`No hay entregas ${nombrePeriodo}`}
                descripcion={`Las entregas aparecen cuando una OC se exporta a Progress.${
                  proxima.data ? ` La próxima está el ${fechaDiaMes(proxima.data)}.` : ''
                }`}
                accion={
                  proxima.data
                    ? {
                        etiqueta: vista === 'semana' ? 'Ir a esa semana' : `Ir a ${nombreMes(mesDe(proxima.data))}`,
                        onClick: () => proxima.data && setSeleccion(proxima.data),
                      }
                    : undefined
                }
              />
            ) : sinCoincidencias ? (
              <Superposicion
                tono="info"
                titulo="Ninguna entrega coincide con la búsqueda"
                descripcion={`No hay entregas de "${busqueda.trim()}" ${nombrePeriodo}.`}
              />
            ) : null}
          </div>
          {vista === 'mes' ? (
            <aside className="flex w-[340px] shrink-0 flex-col gap-4">
              {listaVencidas.length > 0 ? (
                <PanelVencidas vencidas={listaVencidas} onVerTodas={() => setVista('lista')} />
              ) : null}
              <DetalleDia fecha={seleccion} entregas={porFecha.get(seleccion) ?? []} />
            </aside>
          ) : null}
        </div>
      )}
    </div>
  )
}
