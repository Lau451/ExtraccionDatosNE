import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarProductos } from '@/lib/api/productos'
import { listarTerceros } from '@/lib/api/terceros'
import { listarProveedoresProducto } from '@/lib/api/pcp'
import { AgregarProveedorProductoDialog } from './AgregarProveedorProductoDialog'
import { pcpQueryKeys } from './queryKeys'
import { PCP_WRITE_ROLES, puedeRol } from './roles'

export function GestionCatalogoProveedores() {
  const { perfil } = useAuth()
  const [productoSeleccionado, setProductoSeleccionado] = useState('')
  const { data: productos = [], isPending: productosPendientes } = useQuery({ queryKey: ['productos'], queryFn: listarProductos })
  const { data: terceros = [] } = useQuery({ queryKey: ['terceros'], queryFn: listarTerceros })
  const sinProductos = !productosPendientes && productos.length === 0
  const productoId = productoSeleccionado || productos[0]?.id || ''
  const { data: asociaciones = [], isPending, isError } = useQuery({
    queryKey: pcpQueryKeys.proveedoresProducto(productoId),
    queryFn: () => listarProveedoresProducto(productoId),
    enabled: !!productoId,
  })
  const proveedores = terceros.filter((tercero) => tercero.tiene_rol_proveedor)
  const puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)
  const nombreProveedor = (id: string) => terceros.find((tercero) => tercero.id === id)?.razon_social ?? id

  return (
    <main className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-balance text-xl font-semibold text-navy">Catálogo de proveedores</h1>
          <p className="text-sm text-slate-500">Asociaciones por producto</p>
        </div>
        {puedeEscribir && productoId ? (
          <AgregarProveedorProductoDialog productoId={productoId} proveedores={proveedores} />
        ) : null}
      </header>
      <label className="mb-5 block max-w-md text-sm text-slate-600">
        Producto
        <select
          aria-label="Producto"
          value={productoId}
          onChange={(event) => setProductoSeleccionado(event.target.value)}
          disabled={sinProductos}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
        >
          {productos.map((producto) => <option key={producto.id} value={producto.id}>{producto.codigo_interno} — {producto.nombre}</option>)}
        </select>
      </label>
      {sinProductos ? <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-500">No hay productos disponibles.</p> : null}
      {!sinProductos && isPending ? <p className="text-sm text-slate-500">Cargando proveedores…</p> : null}
      {!sinProductos && isError ? <p role="alert" className="text-sm text-red-600">No se pudo cargar el catálogo.</p> : null}
      {!sinProductos && !isPending && !isError && asociaciones.length === 0 ? <p className="rounded-md bg-slate-50 p-4 text-sm text-slate-500">No hay proveedores asociados a este producto.</p> : null}
      {!sinProductos && !isPending && !isError && asociaciones.length > 0 ? (
        <ul aria-label="Proveedores asociados" className="divide-y divide-slate-100 text-sm">
          {asociaciones.map((asociacion) => <li key={asociacion.id} className="py-3 font-medium text-navy">{nombreProveedor(asociacion.proveedor_id)}</li>)}
        </ul>
      ) : null}
    </main>
  )
}
