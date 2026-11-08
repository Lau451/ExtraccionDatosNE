import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarCategorias, listarMarcas, listarProductos, type Clasificacion } from '@/lib/api/productos'
import { GestionCategoriasDialog } from './GestionCategoriasDialog'

const CLASIFICACIONES = [
  'medicamento', 'descartable', 'solucion', 'nutricion', 'equipamiento', 'reactivo', 'cosmetico', 'otro',
]

const PAGE_SIZE = 50
const DEBOUNCE_BUSQUEDA_MS = 300

export function GestionProductos() {
  const { puede } = useAuth()
  const [texto, setTexto] = useState('')
  const [textoBuscado, setTextoBuscado] = useState('')
  const [categoriaId, setCategoriaId] = useState('')
  const [clasificacion, setClasificacion] = useState('')
  const [pagina, setPagina] = useState(1)

  // Debounce manual: no hace falta una dependencia nueva para esto.
  useEffect(() => {
    const id = setTimeout(() => setTextoBuscado(texto.trim()), DEBOUNCE_BUSQUEDA_MS)
    return () => clearTimeout(id)
  }, [texto])

  // Cambiar de búsqueda o de filtro vuelve a página 1 -- si no, se puede
  // quedar mostrando una página vacía de un resultado más chico.
  useEffect(() => {
    setPagina(1)
  }, [textoBuscado, categoriaId, clasificacion])

  const puedeEscribirCategorias = puede('productos.categorias.escribir')

  const { data, isPending } = useQuery({
    queryKey: ['productos', { q: textoBuscado, categoriaId, clasificacion, pagina }],
    queryFn: () =>
      listarProductos({
        q: textoBuscado || undefined,
        categoriaId: categoriaId || undefined,
        clasificacion: (clasificacion || undefined) as Clasificacion | undefined,
        page: pagina,
        pageSize: PAGE_SIZE,
      }),
    // Al cambiar de página/filtro/búsqueda, mantiene la tabla anterior visible
    // mientras llega la nueva en vez de tirarla y mostrar "Cargando…".
    placeholderData: keepPreviousData,
  })
  const { data: categorias } = useQuery({ queryKey: ['categorias'], queryFn: listarCategorias })
  const { data: marcas } = useQuery({ queryKey: ['marcas'], queryFn: listarMarcas })

  const nombreCategoria = (id: string | null) => categorias?.find((c) => c.id === id)?.nombre ?? '—'
  const nombreMarca = (id: string | null) => marcas?.find((m) => m.id === id)?.nombre ?? '—'

  const productosFiltrados = data?.items ?? []
  const total = data?.total ?? 0
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-navy">Productos</h1>
          <p className="mt-1 text-sm text-slate-500">Los productos se dan de alta y se editan en Progress.</p>
        </div>
        <GestionCategoriasDialog puedeEscribir={puedeEscribirCategorias} />
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
              <th className="py-2 font-medium">Marca</th>
              <th className="py-2 font-medium">Estado</th>
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
                <td className="py-2 text-slate-500">{nombreMarca(producto.marca_id)}</td>
                <td className="py-2">
                  <span className={producto.activo ? 'text-emerald-600' : 'text-slate-400'}>
                    {producto.activo ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!isPending && total > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
          <span>
            {total} {total === 1 ? 'producto' : 'productos'} — página {pagina} de {totalPaginas}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={pagina <= 1}
              onClick={() => setPagina((p) => p - 1)}
              className="rounded-md border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Anterior
            </button>
            <button
              type="button"
              disabled={pagina >= totalPaginas}
              onClick={() => setPagina((p) => p + 1)}
              className="rounded-md border border-slate-300 px-3 py-1 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
