import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarTerceros, type Tercero } from '@/lib/api/terceros'
import { CrearTerceroDialog } from './CrearTerceroDialog'
import { GestionSectoresDialog } from './GestionSectoresDialog'
import { GestionCondicionesPagoDialog } from './GestionCondicionesPagoDialog'
import { GestionFormasPagoDialog } from './GestionFormasPagoDialog'
import { CATALOGOS_COMERCIALES_WRITE_ROLES, TERCEROS_WRITE_ROLES, puedeRol } from './roles'

type FiltroRol = 'todos' | 'clientes' | 'proveedores' | 'ambos'

const FILTROS_ROL: { value: FiltroRol; label: string }[] = [
  { value: 'todos', label: 'Todos' },
  { value: 'clientes', label: 'Solo clientes' },
  { value: 'proveedores', label: 'Solo proveedores' },
  { value: 'ambos', label: 'Ambos' },
]

function badgeRol(tercero: Tercero): { texto: string; clase: string } {
  if (tercero.tiene_rol_cliente && tercero.tiene_rol_proveedor) {
    return { texto: 'Ambos', clase: 'bg-purple-100 text-purple-700' }
  }
  if (tercero.tiene_rol_cliente) {
    return { texto: 'Cliente', clase: 'bg-blue-100 text-blue-700' }
  }
  if (tercero.tiene_rol_proveedor) {
    return { texto: 'Proveedor', clase: 'bg-amber-100 text-amber-700' }
  }
  return { texto: 'Sin rol', clase: 'bg-slate-100 text-slate-500' }
}

export function GestionTerceros() {
  const { perfil } = useAuth()
  const [texto, setTexto] = useState('')
  const [filtroRol, setFiltroRol] = useState<FiltroRol>('todos')

  const puedeEscribir = puedeRol(perfil?.rol, TERCEROS_WRITE_ROLES)
  const puedeEscribirCatalogos = puedeRol(perfil?.rol, CATALOGOS_COMERCIALES_WRITE_ROLES)

  const { data: terceros, isPending } = useQuery({
    queryKey: ['terceros'],
    queryFn: listarTerceros,
  })

  const tercerosFiltrados = useMemo(() => {
    const textoNormalizado = texto.trim().toLowerCase()
    return (terceros ?? []).filter((tercero) => {
      if (filtroRol === 'clientes' && !(tercero.tiene_rol_cliente && !tercero.tiene_rol_proveedor)) {
        return false
      }
      if (filtroRol === 'proveedores' && !(tercero.tiene_rol_proveedor && !tercero.tiene_rol_cliente)) {
        return false
      }
      if (filtroRol === 'ambos' && !(tercero.tiene_rol_cliente && tercero.tiene_rol_proveedor)) {
        return false
      }
      if (
        textoNormalizado &&
        !tercero.razon_social.toLowerCase().includes(textoNormalizado) &&
        !(tercero.cuit ?? '').toLowerCase().includes(textoNormalizado) &&
        !(tercero.codigo_interno ?? '').toLowerCase().includes(textoNormalizado)
      ) {
        return false
      }
      return true
    })
  }, [terceros, texto, filtroRol])

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-navy">Terceros</h1>
        <div className="flex gap-2">
          <GestionSectoresDialog puedeEscribir={puedeEscribirCatalogos} />
          <GestionCondicionesPagoDialog puedeEscribir={puedeEscribirCatalogos} />
          <GestionFormasPagoDialog puedeEscribir={puedeEscribirCatalogos} />
          {puedeEscribir && (
            <CrearTerceroDialog
              trigger={
                <button
                  type="button"
                  className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white"
                >
                  + Nuevo tercero
                </button>
              }
            />
          )}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="text"
          value={texto}
          onChange={(event) => setTexto(event.target.value)}
          placeholder="Buscar por razón social, CUIT o código…"
          className="w-72 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={filtroRol}
          onChange={(event) => setFiltroRol(event.target.value as FiltroRol)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {FILTROS_ROL.map((opcion) => (
            <option key={opcion.value} value={opcion.value}>
              {opcion.label}
            </option>
          ))}
        </select>
      </div>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Razón social</th>
              <th className="py-2 font-medium">CUIT</th>
              <th className="py-2 font-medium">Código interno</th>
              <th className="py-2 font-medium">Rol</th>
              <th className="py-2 font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {tercerosFiltrados.map((tercero) => {
              const badge = badgeRol(tercero)
              return (
                <tr key={tercero.id} className="border-b border-slate-100">
                  <td className="py-2">
                    <Link
                      to="/terceros/$terceroId"
                      params={{ terceroId: tercero.id }}
                      className="font-medium text-navy hover:underline"
                    >
                      {tercero.razon_social}
                    </Link>
                  </td>
                  <td className="py-2 text-slate-500">{tercero.cuit ?? '—'}</td>
                  <td className="py-2 text-slate-500">{tercero.codigo_interno ?? '—'}</td>
                  <td className="py-2">
                    <span className={`rounded-full px-2 py-1 text-xs font-medium ${badge.clase}`}>
                      {badge.texto}
                    </span>
                  </td>
                  <td className="py-2">
                    <span className={tercero.activo ? 'text-emerald-600' : 'text-slate-400'}>
                      {tercero.activo ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
