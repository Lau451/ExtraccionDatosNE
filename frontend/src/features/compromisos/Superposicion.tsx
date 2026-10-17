import clsx from 'clsx'

interface SuperposicionProps {
  tono: 'info' | 'error'
  titulo: string
  descripcion: string
  accion?: { etiqueta: string; onClick: () => void }
}

/** Mensaje centrado sobre la grilla (vacío o error): la grilla sigue visible detrás. */
export function Superposicion({ tono, titulo, descripcion, accion }: SuperposicionProps) {
  return (
    <div
      role={tono === 'error' ? 'alert' : undefined}
      className="absolute inset-0 flex items-center justify-center bg-white/80"
    >
      <div className="flex w-80 flex-col items-center gap-2.5 rounded-lg border border-slate-200 bg-white p-6 text-center shadow-lg shadow-slate-900/5">
        <span
          aria-hidden="true"
          className={clsx(
            'flex size-10 items-center justify-center rounded-full text-lg font-semibold',
            tono === 'error' ? 'bg-red-50 text-red-700' : 'bg-sky-50 text-accent',
          )}
        >
          {tono === 'error' ? '!' : '✓'}
        </span>
        <p className="text-[15px] font-semibold text-slate-900">{titulo}</p>
        <p className="text-[13px] leading-snug text-slate-600">{descripcion}</p>
        {accion ? (
          <button
            type="button"
            onClick={accion.onClick}
            className={clsx(
              'mt-1 rounded-md px-3.5 py-2 text-[13px] font-medium',
              tono === 'error'
                ? 'bg-accent text-white hover:bg-sky-800'
                : 'border border-slate-200 bg-white text-slate-900 hover:bg-slate-50',
            )}
          >
            {accion.etiqueta}
          </button>
        ) : null}
      </div>
    </div>
  )
}
