import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { eliminarProducto, listarCategorias, listarProductos, type Producto } from '@/lib/api/productos'
import { CrearProductoDialog } from './CrearProductoDialog'
import { GestionCategoriasDialog } from './GestionCategoriasDialog'
import { CATEGORIAS_WRITE_ROLES, PRODUCTOS_WRITE_ROLES, puedeRol } from './roles'

const CLASIFICACIONES = ['medicamento', 'descartable', 'insumo', 'equipamiento', 'perfumeria', 'otro']

export function GestionProductos() {
  const { perfil } = useAuth()
  const queryClient = useQueryClient()
  const [aEliminar, setAEliminar] = useState<Producto | null>(null)
  const [texto, setTexto] = useState('')
  const [categoriaId, setCategoriaId] = useState('')
  const [clasificacion, setClasificacion] = useState('')

  const puedeEscribir = puedeRol(perfil?.rol, PRODUCTOS_WRITE_ROLES)
  const puedeEscribirCategorias = puedeRol(perfil?.rol, CATEGORIAS_WRITE_ROLES)

  const { data: productos, isPending } = useQuery({
    queryKey: ['productos'],
    queryFn: listarProductos,
  })
  const { data: categorias } = useQuery({ queryKey: ['categorias'], queryFn: listarCategorias })

  const eliminarMutation = useMutation({
    mutationFn: (id: string) => eliminarProducto(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['productos'] })
      setAEliminar(null)
    },
  })

  const nombreCategoria = (id: string | null) => categorias?.find((c) => c.id === id)?.nombre ?? '—'

  const productosFiltrados = useMemo(() => {
    const textoNormalizado = texto.trim().toLowerCase()
    return (productos ?? []).filter((producto) => {
      if (categoriaId && producto.categoria_id !== categoriaId) return false
      if (clasificacion && producto.clasificacion !== clasificacion) return false
      if (
        textoNormalizado &&
        !producto.nombre.toLowerCase().includes(textoNormalizado) &&
        !producto.codigo_interno.toLowerCase().includes(textoNormalizado)
      ) {
        return false
      }
      return true
    })
  }, [productos, texto, categoriaId, clasificacion])

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-navy">Productos</h1>
        <div className="flex gap-2">
          <GestionCategoriasDialog puedeEscribir={puedeEscribirCategorias} />
          {puedeEscribir && (
            <CrearProductoDialog
              categorias={categorias ?? []}
              trigger={
                <button
                  type="button"
                  className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white"
                >
                  + Nuevo producto
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
          placeholder="Buscar por nombre o código…"
          className="w-64 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={categoriaId}
          onChange={(event) => setCategoriaId(event.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Todas las categorías</option>
          {categorias?.map((categoria) => (
            <option key={categoria.id} value={categoria.id}>
              {categoria.nombre}
            </option>
          ))}
        </select>
        <select
          value={clasificacion}
          onChange={(event) => setClasificacion(event.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Todas las clasificaciones</option>
          {CLASIFICACIONES.map((opcion) => (
            <option key={opcion} value={opcion}>
              {opcion}
            </option>
          ))}
        </select>
      </div>

      {eliminarMutation.isError && (
        <p className="mb-4 text-sm text-red-600">
          {eliminarMutation.error instanceof Error
            ? eliminarMutation.error.message
            : 'No se pudo eliminar el producto.'}
        </p>
      )}

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Código</th>
              <th className="py-2 font-medium">Nombre</th>
              <th className="py-2 font-medium">Categoría</th>
              <th className="py-2 font-medium">Clasificación</th>
              <th className="py-2 font-medium">Laboratorio</th>
              <th className="py-2 font-medium">Estado</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {productosFiltrados.map((producto) => (
              <tr key={producto.id} className="border-b border-slate-100">
                <td className="py-2">{producto.codigo_interno}</td>
                <td className="py-2">
                  <Link
                    to="/productos/$productoId"
                    params={{ productoId: producto.id }}
                    className="font-medium text-navy hover:underline"
                  >
                    {producto.nombre}
                  </Link>
                </td>
                <td className="py-2 text-slate-500">{nombreCategoria(producto.categoria_id)}</td>
                <td className="py-2 text-slate-500">{producto.clasificacion ?? '—'}</td>
                <td className="py-2 text-slate-500">{producto.laboratorio ?? '—'}</td>
                <td className="py-2">
                  <span className={producto.activo ? 'text-emerald-600' : 'text-slate-400'}>
                    {producto.activo ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
                <td className="py-2 text-right space-x-3">
                  {puedeEscribir && (
                    <>
                      <CrearProductoDialog
                        producto={producto}
                        categorias={categorias ?? []}
                        trigger={
                          <button
                            type="button"
                            className="text-sm font-medium text-accent hover:underline"
                          >
                            Editar
                          </button>
                        }
                      />
                      <button
                        type="button"
                        onClick={() => setAEliminar(producto)}
                        className="text-sm font-medium text-red-600 hover:underline"
                      >
                        Eliminar
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={aEliminar !== null}
        onOpenChange={(open) => !open && setAEliminar(null)}
        title="Eliminar producto"
        description={`¿Eliminar el producto "${aEliminar?.nombre ?? ''}"? Esta acción no se puede deshacer.`}
        isPending={eliminarMutation.isPending}
        onConfirm={() => aEliminar && eliminarMutation.mutate(aEliminar.id)}
      />
    </div>
  )
}
