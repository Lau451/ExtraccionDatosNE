import type { KeyboardEvent } from 'react'
import clsx from 'clsx'
import { useAutoGrowTextarea } from '../useAutoGrowTextarea'

interface Props {
  fieldId: string
  label: string
  value: string
  error?: string
  disabled?: boolean
  onChange: (valor: string) => void
  onEnter?: () => void
  onEscape?: () => void
  inputRef?: (el: HTMLInputElement | HTMLTextAreaElement | null) => void
  /** T3: descripción usa un textarea auto-creciente en vez de un <input> de
   * una sola línea -- así el texto completo queda visible sin truncar. Enter
   * conserva el mismo contrato que el <input> (mueve foco, nunca inserta un
   * salto de línea). */
  multiline?: boolean
  /** T3: columnas numéricas (cantidad, precio_unitario, etc.) -- alineadas a
   * la derecha con `tabular-nums` para que los dígitos no bailen entre filas. */
  numeric?: boolean
}

/** Input + validación por celda (D5). `aria-invalid`/`aria-describedby` van
 * en la celda misma -- el mensaje de error vive junto al campo, no agrupado
 * arriba (design.md §9.2, "accesibilidad de la tabla editable"). */
export function CeldaEditable({
  fieldId,
  label,
  value,
  error,
  disabled,
  onChange,
  onEnter,
  onEscape,
  inputRef,
  multiline = false,
  numeric = false,
}: Props) {
  const autoGrow = useAutoGrowTextarea(value)

  function manejarTeclado(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    // Tab/Shift+Tab: orden natural del DOM, sin manejo custom.
    if (event.key === 'Enter') {
      // Con textarea, Enter NUNCA inserta un salto de línea -- mismo contrato
      // que el <input> de siempre: mueve el foco al mismo campo de la fila
      // siguiente (TablaEditable.enfocar).
      event.preventDefault()
      onEnter?.()
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      onEscape?.()
    }
  }

  const clasesComunes = clsx(
    'w-full rounded-md border px-2 py-1 text-sm',
    numeric && 'text-right tabular-nums',
    disabled
      ? 'border-slate-200 bg-slate-100 text-slate-400 line-through'
      : error
        ? 'border-red-400 bg-red-50 text-red-900'
        : 'border-slate-300',
  )

  return (
    <div>
      {multiline ? (
        <textarea
          ref={(el) => {
            autoGrow.ref(el)
            inputRef?.(el)
          }}
          id={fieldId}
          aria-label={label}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={manejarTeclado}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          rows={1}
          className={clsx(clasesComunes, 'resize-none overflow-hidden leading-normal')}
        />
      ) : (
        <input
          ref={inputRef}
          id={fieldId}
          aria-label={label}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={manejarTeclado}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          className={clasesComunes}
        />
      )}
      {error && (
        <p id={`${fieldId}-error`} className="mt-0.5 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}
