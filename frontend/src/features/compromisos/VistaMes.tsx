import clsx from 'clsx'
import type { EntregaCompromiso } from './agruparCompromisos'
import { diaSemanaLargo, fechaDiaMes, mesDe, semanasDelMes } from './fechas'
import { contarEntregas } from './textos'

const DIAS_CORTOS = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
const CHIPS_POR_DIA = 3

export function ChipEntrega({ entrega }: { entrega: EntregaCompromiso }) {
  const vencida = entrega.situacion === 'vencida'
  return (
    <span
      data-testid="chip-entrega"
      data-situacion={entrega.situacion}
      title={vencida ? 'Vencida' : undefined}
      className={clsx(
        'flex items-center gap-1 overflow-hidden whitespace-nowrap rounded border-l-[3px] px-1.5 py-0.5 text-[11px]',
        vencida ? 'border-red-300 bg-red-50 text-red-900' : 'border-sky-200 bg-sky-50 text-sky-900',
      )}
    >
      <span className={clsx('font-semibold', vencida ? 'text-red-800' : 'text-sky-800')}>{entrega.numero_oc}</span>
      {' · '}
      <span className="truncate">{entrega.cliente ?? 'Sin cliente'}</span>
    </span>
  )
}

interface VistaMesProps {
  mes: string
  hoy: string
  seleccion: string
  porFecha: Map<string, EntregaCompromiso[]>
  cargando?: boolean
  onSeleccionar: (fecha: string) => void
}

/** Barras grises en posiciones fijas mientras llega el período. */
function Esqueleto({ indice }: { indice: number }) {
  return (
    <span aria-hidden="true" className="flex flex-col gap-1">
      {indice % 3 === 1 ? <span className="h-3.5 animate-pulse rounded bg-slate-100" /> : null}
      {indice % 5 === 2 ? <span className="h-3.5 animate-pulse rounded bg-slate-100" /> : null}
    </span>
  )
}

/** Grilla lunes a domingo con todas las semanas del mes: hasta 3 chips por día y "+N más". */
export function VistaMes({ mes, hoy, seleccion, porFecha, cargando = false, onSeleccionar }: VistaMesProps) {
  return (
    <div
      aria-busy={cargando}
      className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white"
    >
      {cargando ? (
        <p role="status" className="sr-only">
          Cargando compromisos…
        </p>
      ) : null}
      <div className="grid grid-cols-7 border-b border-slate-200">
        {DIAS_CORTOS.map((nombre) => (
          <div key={nombre} className="px-2.5 py-2 text-[11px] font-semibold tracking-wide text-slate-400">
            {nombre}
          </div>
        ))}
      </div>
      {semanasDelMes(mes).map((semana, numeroSemana) => (
        <div key={semana[0]} className="grid flex-1 grid-cols-7 border-b border-slate-200 last:border-b-0">
          {semana.map((fecha, indice) => {
            const entregas = porFecha.get(fecha) ?? []
            const fueraDeMes = mesDe(fecha) !== mes
            const esHoy = fecha === hoy
            const seleccionado = fecha === seleccion
            return (
              <button
                key={fecha}
                type="button"
                onClick={() => onSeleccionar(fecha)}
                aria-label={`${diaSemanaLargo(fecha)} ${fechaDiaMes(fecha)}, ${contarEntregas(entregas.length)}`}
                aria-pressed={seleccionado}
                aria-current={esHoy ? 'date' : undefined}
                data-fuera-de-mes={fueraDeMes}
                className={clsx(
                  'flex min-h-28 min-w-0 flex-col gap-1 p-1.5 text-left outline-offset-[-2px] focus-visible:outline-2 focus-visible:outline-accent',
                  indice < 6 && 'border-r border-slate-200',
                  indice >= 5 && !seleccionado && 'bg-slate-50/40',
                  seleccionado && 'bg-sky-50 outline-[1.5px] outline-accent',
                )}
              >
                <span className="flex items-center justify-between">
                  <span
                    className={clsx(
                      'flex size-6 items-center justify-center rounded-full text-xs tabular-nums',
                      esHoy ? 'bg-accent font-semibold text-white' : fueraDeMes ? 'text-slate-400' : 'font-medium text-slate-900',
                    )}
                  >
                    {Number(fecha.slice(8, 10))}
                  </span>
                  {esHoy ? <span className="text-[10px] font-semibold text-accent">Hoy</span> : null}
                </span>
                {cargando ? <Esqueleto indice={numeroSemana * 7 + indice} /> : null}
                <span className={clsx('flex min-w-0 flex-col gap-1', fueraDeMes && 'opacity-60')}>
                  {entregas.slice(0, CHIPS_POR_DIA).map((entrega) => (
                    <ChipEntrega key={entrega.entrega_oc_id} entrega={entrega} />
                  ))}
                  {entregas.length > CHIPS_POR_DIA ? (
                    <span className="text-[11px] font-medium text-accent">+{entregas.length - CHIPS_POR_DIA} más</span>
                  ) : null}
                </span>
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
