import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { listarCompromisos } from '@/lib/api/compromisos'
import { ApiError } from '@/lib/api/presupuestacion'
import { agruparCompromisos, agruparEntregas, filtrarEntregas, type EntregaCompromiso } from './agruparCompromisos'

// 'YYYY-MM-DD' se parte a mano: new Date('YYYY-MM-DD') parsea como UTC y en
// Argentina (UTC-3) mostraría el día anterior.
function formatearFecha(iso: string | null): string {
  if (!iso) return 'Sin fecha'
  const [anio, mes, dia] = iso.split('-')
  return `${dia}/${mes}/${anio}`
}

function formatearMes(clave: string): string {
  if (clave === 'sin-fecha') return 'Sin fecha'
  const [anio, mes] = clave.split('-').map(Number)
  return new Date(Date.UTC(anio, mes - 1, 1)).toLocaleDateString('es-AR', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

function TarjetaEntrega({ entrega }: { entrega: EntregaCompromiso }) {
  const atraso = `${entrega.dias_atraso} ${entrega.dias_atraso === 1 ? 'día' : 'días'} de atraso`
  return (
    <li className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
        <span className="font-medium text-slate-900">{entrega.cliente ?? 'Sin cliente'}</span>
        <Link
          to="/ordenes-compra/$ordenCompraId"
          params={{ ordenCompraId: entrega.orden_compra_id }}
          className="text-accent hover:underline"
        >
          {entrega.numero_oc}
        </Link>
        <span className="text-slate-500">Entrega {entrega.numero_entrega}</span>
        {entrega.situacion === 'vencida' ? (
          <span className="text-red-700">
            {formatearFecha(entrega.fecha_entrega_planificada)} · {atraso}
          </span>
        ) : null}
      </div>
      <ul className="mt-2 space-y-1 text-sm text-slate-700">
        {entrega.renglones.map((renglon, indice) => (
          <li key={`${renglon.numero_renglon ?? 'x'}-${indice}`} className="flex justify-between gap-4">
            <span>{renglon.descripcion ?? renglon.codigo_articulo ?? 'Sin descripción'}</span>
            <span className="tabular-nums">{renglon.cantidad_planificada.toLocaleString('es-AR')}</span>
          </li>
        ))}
      </ul>
    </li>
  )
}

/** Vista "Lista": la agenda original (vencidas primero, después por mes y fecha)
 * sobre el rango por defecto del backend. `filtro` es la búsqueda "cliente u OC". */
export function VistaLista({ filtro }: { filtro: string }) {
  const query = useQuery({ queryKey: ['compromisos-entregas'], queryFn: () => listarCompromisos() })

  if (query.isPending) {
    return <p className="text-sm text-slate-500">Cargando compromisos…</p>
  }

  if (query.isError) {
    const mensaje = query.error instanceof ApiError ? query.error.message : 'No se pudieron cargar los compromisos.'
    return (
      <p role="alert" className="text-sm text-red-700">
        {mensaje}
      </p>
    )
  }

  const visibles = new Set(filtrarEntregas(agruparEntregas(query.data), filtro).map((e) => e.entrega_oc_id))
  const agenda = agruparCompromisos(query.data.filter((fila) => visibles.has(fila.entrega_oc_id)))
  const vacia = agenda.vencidas.length === 0 && agenda.meses.length === 0

  return (
    <div className="space-y-8">
      {vacia ? <p className="text-sm text-slate-500">No hay entregas comprometidas en el período.</p> : null}

      {agenda.vencidas.length > 0 ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-red-700">Vencidas sin confirmar</h2>
          <ul className="space-y-2">
            {agenda.vencidas.map((entrega) => (
              <TarjetaEntrega key={entrega.entrega_oc_id} entrega={entrega} />
            ))}
          </ul>
        </section>
      ) : null}

      {agenda.meses.map((mes) => (
        <section key={mes.clave}>
          <h2 className="mb-3 text-lg font-semibold capitalize text-slate-900">{formatearMes(mes.clave)}</h2>
          <div className="space-y-4">
            {mes.fechas.map((grupo) => (
              <div key={grupo.fecha ?? 'sin-fecha'}>
                <h3 className="mb-2 text-sm font-medium text-slate-600">{formatearFecha(grupo.fecha)}</h3>
                <ul className="space-y-2">
                  {grupo.entregas.map((entrega) => (
                    <TarjetaEntrega key={entrega.entrega_oc_id} entrega={entrega} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
