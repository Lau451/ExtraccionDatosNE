import { useQuery } from '@tanstack/react-query'
import { listarExtracciones } from '@/lib/api/extracciones'
import { PendientesTable } from './components/PendientesTable'

export function ValidarExtraccionListado() {
  // D-VALIDAREXTRACCION (design.md §9.3) -- POST /procesar persiste en un
  // BackgroundTask del lado de `services/extraccion`; un usuario que sube un
  // documento y navega directo acá puede no verlo todavía. staleTime: 0 +
  // refetchOnWindowFocus (default de TanStack Query) + botón "Actualizar"
  // cubren el caso sin polling -- ver conclusión doble en design.md.
  const query = useQuery({
    queryKey: ['extracciones', { validado: false }],
    queryFn: () => listarExtracciones({ validado: false }),
    staleTime: 0,
  })

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Validar extracción</h1>
          <p className="text-sm text-slate-500">Extracciones pendientes de revisión</p>
        </div>
        <button
          type="button"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {query.isFetching ? 'Actualizando…' : 'Actualizar'}
        </button>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {query.isPending && <p className="text-sm text-slate-500">Cargando…</p>}

        {query.isError && (
          <p className="text-sm text-red-600">
            {query.error instanceof Error ? query.error.message : 'No se pudo cargar el listado.'}
          </p>
        )}

        {query.data && <PendientesTable extracciones={query.data} />}
      </div>
    </div>
  )
}
