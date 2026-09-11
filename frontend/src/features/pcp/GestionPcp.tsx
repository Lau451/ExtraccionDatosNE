import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarPcp, type EstadoPcp } from '@/lib/api/pcp'
import { CrearPcpDialog } from './CrearPcpDialog'
import { pcpQueryKeys } from './queryKeys'
import { PCP_WRITE_ROLES, puedeRol } from './roles'

const ESTADOS: { value: EstadoPcp; label: string }[] = [
  { value: 'nueva', label: 'Nueva' },
  { value: 'en_gestion', label: 'En gestión' },
  { value: 'esperando_respuesta', label: 'Esperando respuesta' },
  { value: 'cerrada', label: 'Cerrada' },
]

export function GestionPcp() {
  const { perfil } = useAuth()
  const [estado, setEstado] = useState<EstadoPcp | ''>('')
  const [fechaDesde, setFechaDesde] = useState('')
  const [fechaHasta, setFechaHasta] = useState('')
  const filtros = {
    ...(estado && { estado }),
    ...(fechaDesde && { fecha_desde: fechaDesde }),
    ...(fechaHasta && { fecha_hasta: fechaHasta }),
  }
  const tieneFiltros = Object.keys(filtros).length > 0
  const { data: pcps = [], isPending, isError } = useQuery({
    queryKey: pcpQueryKeys.lista(tieneFiltros ? filtros : undefined),
    queryFn: () => listarPcp(tieneFiltros ? filtros : undefined),
  })
  const puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)

  return (
    <main className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-balance text-xl font-semibold text-navy">Gestión de PCP</h1>
          <p className="text-sm text-slate-500">Consultas de compra en curso</p>
        </div>
        {puedeEscribir && <CrearPcpDialog />}
      </header>

      <section aria-label="Filtros" className="mb-5 flex flex-wrap gap-3">
        <label className="text-sm text-slate-600">
          Estado
          <select
            aria-label="Estado"
            value={estado}
            onChange={(event) => setEstado(event.target.value as EstadoPcp | '')}
            className="ml-2 rounded-md border border-slate-300 px-2 py-2"
          >
            <option value="">Todos</option>
            {ESTADOS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Desde
          <input
            type="date"
            value={fechaDesde}
            onChange={(event) => setFechaDesde(event.target.value)}
            className="ml-2 rounded-md border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="text-sm text-slate-600">
          Hasta
          <input
            type="date"
            value={fechaHasta}
            onChange={(event) => setFechaHasta(event.target.value)}
            className="ml-2 rounded-md border border-slate-300 px-2 py-1"
          />
        </label>
      </section>

      {isPending ? <p className="text-sm text-slate-500">Cargando PCP…</p> : null}
      {isError ? <p role="alert" className="text-sm text-red-600">No se pudo cargar los PCP.</p> : null}
      {!isPending && !isError && pcps.length === 0 ? (
        <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-500">
          No hay PCP para los filtros elegidos.
        </p>
      ) : null}
      {!isPending && !isError && pcps.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-slate-500">
              <th className="py-2">Presupuesto</th>
              <th className="py-2">Estado</th>
              <th className="py-2">Entrega solicitada</th>
            </tr>
          </thead>
          <tbody>
            {pcps.map((pcp) => (
              <tr key={pcp.id} className="border-b border-slate-100">
                <td className="py-3">
                  <Link
                    to="/pcp/$pcpId"
                    params={{ pcpId: pcp.id }}
                    className="font-medium text-navy hover:underline"
                  >
                    {pcp.presupuesto_id}
                  </Link>
                </td>
                <td className="py-3">
                  {ESTADOS.find((item) => item.value === pcp.estado)?.label}
                </td>
                <td className="py-3 text-slate-500">{pcp.fecha_entrega_solicitada ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </main>
  )
}
