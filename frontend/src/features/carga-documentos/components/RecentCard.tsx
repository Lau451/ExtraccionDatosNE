import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { listarDocumentosRecientes } from '@/lib/api/extraccion'

const STATUS_STYLES: Record<string, string> = {
  completado: 'bg-emerald-100 text-emerald-700',
  procesando: 'bg-amber-100 text-amber-700',
  error: 'bg-red-100 text-red-700',
}

export function RecentCard() {
  const { data, isLoading } = useQuery({
    queryKey: ['documentos-recientes'],
    queryFn: () => listarDocumentosRecientes(),
  })

  const documentos = data?.documentos.slice(0, 3) ?? []

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-sm font-semibold text-slate-900">Cargas recientes</h2>

      {isLoading && <p className="text-sm text-slate-500">Cargando…</p>}

      {!isLoading && documentos.length === 0 && (
        <p className="text-sm text-slate-500">Todavía no se cargaron documentos.</p>
      )}

      <ul className="space-y-3">
        {documentos.map((doc) => (
          <li key={doc.id} className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-900">{doc.source_filename}</p>
              <p className="text-xs text-slate-500">{doc.licitacion?.nombre ?? 'Sin licitación'}</p>
            </div>
            <span
              className={clsx(
                'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
                STATUS_STYLES[doc.status] ?? 'bg-slate-100 text-slate-600',
              )}
            >
              {doc.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
