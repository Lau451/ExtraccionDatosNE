import { ConfirmDialog } from '@/components/ConfirmDialog'
import type { DocumentType } from '@/lib/api/extracciones'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  modificadas: number
  borradas: number
  agregadas: number
  documentType: DocumentType
  isPending: boolean
  onConfirm: () => void
}

function plural(cantidad: number, singular: string, plural: string) {
  return `${cantidad} ${cantidad === 1 ? singular : plural}`
}

/** Wrapper de ConfirmDialog.tsx -- resume el impacto real antes de ejecutar
 * (D5): N modificadas, N borradas, N agregadas.
 *
 * Nota de alcance (ver reporte de apply): D5/design.md §9.2 piden advertir SI
 * el proceso ya tiene una comparativa vigente, pero ningún endpoint expone esa
 * información antes de confirmar -- el backend solo la informa DESPUÉS, en
 * `reemplazo_version_anterior` (demasiado tarde para una advertencia previa).
 * Se usa una advertencia estática para document_type="comparativa" en su lugar,
 * en vez de un chequeo condicional inexistente en la API actual. */
export function ConfirmarValidacionDialog({
  open,
  onOpenChange,
  modificadas,
  borradas,
  agregadas,
  documentType,
  isPending,
  onConfirm,
}: Props) {
  const partes = [
    modificadas > 0 && plural(modificadas, 'fila modificada', 'filas modificadas'),
    borradas > 0 && plural(borradas, 'fila borrada', 'filas borradas'),
    agregadas > 0 && plural(agregadas, 'fila agregada', 'filas agregadas'),
  ].filter((parte): parte is string => Boolean(parte))

  const resumen = partes.length > 0 ? partes.join(', ') : 'sin cambios respecto al documento original'

  const advertenciaReemplazo =
    documentType === 'comparativa'
      ? ' Si este proceso ya tiene una comparativa vigente, esta validación la reemplazará (quedará invalidada).'
      : ''

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Confirmar validación"
      description={`Se van a materializar las filas: ${resumen}.${advertenciaReemplazo} Esta acción no se puede deshacer.`}
      confirmLabel="Confirmar validación"
      pendingLabel="Validando…"
      isPending={isPending}
      onConfirm={onConfirm}
    />
  )
}
