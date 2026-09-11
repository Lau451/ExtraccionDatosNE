import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { obtenerDetalleRenglon } from '@/lib/api/pcp'
import { ComparacionProveedoresTable } from './ComparacionProveedoresTable'
import { pcpQueryKeys } from './queryKeys'
import { PCP_WRITE_ROLES, puedeRol } from './roles'
import { SeleccionProveedoresSection } from './SeleccionProveedoresSection'
import { SugerenciasPanel } from './SugerenciasPanel'

export function RenglonDetalle({ pcpId, renglonId }: { pcpId: string, renglonId: string }) {
  const { perfil } = useAuth()
  const detalleQuery = useQuery({
    queryKey: pcpQueryKeys.renglon(pcpId, renglonId),
    queryFn: () => obtenerDetalleRenglon(pcpId, renglonId),
  })

  if (detalleQuery.isPending) return <p className="p-8 text-sm text-slate-500">Cargando renglón…</p>
  if (detalleQuery.isError || !detalleQuery.data) return <p role="alert" className="p-8 text-sm text-red-600">No se pudo cargar el detalle del renglón.</p>

  const { producto, proveedores_catalogados: proveedores } = detalleQuery.data
  const puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)

  return (
    <main className="p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">Renglón {detalleQuery.data.renglon.item_proceso_id}</p>
          <h1 className="text-balance text-xl font-semibold text-navy">{producto?.nombre ?? 'Producto no identificado'}</h1>
          {producto ? <p className="mt-1 text-sm text-slate-500">{producto.codigo_interno}</p> : null}
        </div>
      </header>
      <SeleccionProveedoresSection
        pcpId={pcpId}
        renglonId={renglonId}
        proveedores={proveedores}
        puedeEscribir={puedeEscribir}
      />
      <ComparacionProveedoresTable
        pcpId={pcpId}
        renglonId={renglonId}
        proveedores={proveedores}
        puedeEscribir={puedeEscribir}
      />
      <SugerenciasPanel renglonId={renglonId} />
    </main>
  )
}
