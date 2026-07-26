import { Link } from '@tanstack/react-router'
import { MAX_FILAS_EDITABLES } from '../constants'

interface Props {
  rowCount: number
  isPending: boolean
  onConfirmarSinEditar: () => void
}

/** D7 -- por arriba del tope no se trunca en silencio: el usuario ve `row_count`
 * real y las dos únicas acciones son confirmar tal cual (materializa desde el
 * CSV, sin `filas` en el body) o volver sin validar (design.md §7). */
export function DocumentoDemasiadoGrande({ rowCount, isPending, onConfirmarSinEditar }: Props) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-6">
      <h2 className="text-sm font-semibold text-amber-900">Documento demasiado grande para editar</h2>
      <p className="mt-2 text-sm text-amber-800">
        Esta extracción tiene <strong>{rowCount}</strong> filas — por encima del límite de{' '}
        {MAX_FILAS_EDITABLES} filas editables por validación. No se puede editar celda por celda,
        pero podés confirmarla tal cual la leyó la extracción.
      </p>
      <div className="mt-4 flex gap-3">
        <button
          type="button"
          disabled={isPending}
          onClick={onConfirmarSinEditar}
          className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {isPending ? 'Confirmando…' : 'Confirmar sin editar'}
        </button>
        <Link
          to="/validar-extraccion"
          className="rounded-md px-3 py-2 text-sm text-slate-600 hover:underline"
        >
          Volver al listado
        </Link>
      </div>
    </div>
  )
}
