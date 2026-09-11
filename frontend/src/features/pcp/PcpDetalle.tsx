import { Link, Outlet } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarRenglones, listarRenglonesSeleccionados, listarSeleccionesAgrupables, obtenerPcp } from '@/lib/api/pcp'
import { AgruparConsultaDialog } from './AgruparConsultaDialog'
import { CerrarPcpDialog } from './CerrarPcpDialog'
import { CrearRenglonDialog } from './CrearRenglonDialog'
import { EstadoPcpStepper } from './EstadoPcpStepper'
import { pcpQueryKeys } from './queryKeys'
import { PCP_WRITE_ROLES, puedeRol } from './roles'

export function PcpDetalle({ pcpId }: { pcpId: string }) {
  const { perfil } = useAuth()
  const puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)
  const pcpQuery = useQuery({ queryKey: pcpQueryKeys.detalle(pcpId), queryFn: () => obtenerPcp(pcpId) })
  const renglonesQuery = useQuery({ queryKey: pcpQueryKeys.renglones(pcpId), queryFn: () => listarRenglones(pcpId) })
  const seleccionQuery = useQuery({ queryKey: pcpQueryKeys.seleccion(pcpId), queryFn: () => listarRenglonesSeleccionados(pcpId) })
  const seleccionesAgrupablesQuery = useQuery({
    queryKey: pcpQueryKeys.seleccionesAgrupables(pcpId),
    queryFn: () => listarSeleccionesAgrupables(pcpId),
  })

  if (pcpQuery.isPending || renglonesQuery.isPending || seleccionQuery.isPending) return <p className="p-8 text-sm text-slate-500">Cargando PCP…</p>
  if (pcpQuery.isError || renglonesQuery.isError || seleccionQuery.isError || !pcpQuery.data) return <p role="alert" className="p-8 text-sm text-red-600">No se pudo cargar el detalle del PCP.</p>

  const pcp = pcpQuery.data
  const seleccionados = new Set(seleccionQuery.data)
  return (
    <main className="p-8">
      <Link to="/pcp" className="mb-4 inline-block text-sm text-accent hover:underline">← Volver a PCP</Link>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-balance text-xl font-semibold text-navy">PCP {pcp.presupuesto_id}</h1><p className="text-sm text-slate-500">Entrega solicitada: {pcp.fecha_entrega_solicitada ?? '—'}</p></div>
        {puedeEscribir && pcp.estado !== 'cerrada' ? <CerrarPcpDialog pcpId={pcpId} /> : null}
      </header>
      <EstadoPcpStepper pcp={pcp} puedeEscribir={puedeEscribir} />
      <section className="mt-8" aria-labelledby="renglones-title">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="renglones-title" className="text-base font-semibold text-navy">Renglones</h2>
          <div className="flex items-center gap-2">
            {puedeEscribir && (seleccionesAgrupablesQuery.data?.length ?? 0) > 0 ? (
              <AgruparConsultaDialog selecciones={seleccionesAgrupablesQuery.data ?? []} puedeEscribir={puedeEscribir} />
            ) : null}
            {puedeEscribir ? <CrearRenglonDialog pcpId={pcpId} /> : null}
          </div>
        </div>
        {renglonesQuery.data.length === 0 ? <p className="mt-3 text-sm text-slate-500">Este PCP todavía no tiene renglones.</p> : (
          <ul className="mt-3 divide-y divide-slate-100 rounded-lg bg-white shadow-sm">
            {renglonesQuery.data.map((renglon) => <li key={renglon.id} className="flex items-center justify-between gap-3 p-4 text-sm">
              <a href={`/pcp/${pcpId}/renglones/${renglon.id}`} className="font-medium text-navy hover:underline">Ítem {renglon.item_proceso_id}</a>
              <span className={seleccionados.has(renglon.id) ? 'rounded-full bg-emerald-100 px-2 py-1 text-emerald-800' : 'rounded-full bg-amber-100 px-2 py-1 text-amber-800'}>{seleccionados.has(renglon.id) ? 'Negociado' : 'Pendiente'}</span>
            </li>)}
          </ul>
        )}
      </section>
      <Outlet />
    </main>
  )
}
