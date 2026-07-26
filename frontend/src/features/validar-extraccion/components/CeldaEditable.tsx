import clsx from 'clsx'

interface Props {
  fieldId: string
  label: string
  value: string
  error?: string
  disabled?: boolean
  onChange: (valor: string) => void
  onEnter?: () => void
  onEscape?: () => void
  inputRef?: (el: HTMLInputElement | null) => void
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
}: Props) {
  return (
    <div>
      <input
        ref={inputRef}
        id={fieldId}
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          // Tab/Shift+Tab: orden natural del DOM, sin manejo custom.
          if (event.key === 'Enter') {
            event.preventDefault()
            onEnter?.()
          }
          if (event.key === 'Escape') {
            event.preventDefault()
            onEscape?.()
          }
        }}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : undefined}
        className={clsx(
          'w-full rounded-md border px-2 py-1 text-sm',
          disabled
            ? 'border-slate-200 bg-slate-100 text-slate-400 line-through'
            : error
              ? 'border-red-400 bg-red-50 text-red-900'
              : 'border-slate-300',
        )}
      />
      {error && (
        <p id={`${fieldId}-error`} className="mt-0.5 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}
