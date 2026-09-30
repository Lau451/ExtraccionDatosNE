import { useEffect, useState } from 'react'

// Enteros para la cantidad de entregas; hasta dos decimales para cantidades
// (NUMERIC(12,2)), con punto o coma.
const PATRON_ENTERO = /^\d*$/
const PATRON_DECIMAL = /^\d*([.,]\d{0,2})?$/

function aNumero(texto: string): number | null {
  if (texto === '' || texto === '.' || texto === ',') return null
  return Number(texto.replace(',', '.'))
}

interface CampoNumericoProps {
  valor: number
  onCambiar: (valor: number) => void
  ariaLabel: string
  decimales?: boolean
  // Vacío = 0 (cantidades). Si es false, un campo vacío no se aplica y al
  // salir vuelve al último valor válido (cantidad de entregas).
  vacioEsCero?: boolean
  id?: string
  className?: string
}

/** Campo de texto con teclado numérico, sin las flechitas de `type="number"`.
 * Guarda el texto que se está escribiendo aparte del número, para poder
 * borrarlo entero y escribir otro (un `type="number"` controlado vuelve a
 * mostrar "0" o el mínimo apenas se vacía). Al hacer foco selecciona todo. */
export function CampoNumerico({
  valor,
  onCambiar,
  ariaLabel,
  decimales = false,
  vacioEsCero = false,
  id,
  className,
}: CampoNumericoProps) {
  const [texto, setTexto] = useState(String(valor))

  // Sincroniza cambios que vienen de afuera ("usar N", recálculo al cambiar la
  // cantidad de entregas, límites aplicados por el padre) sin pisar lo que se
  // está escribiendo cuando ya representa el mismo número.
  useEffect(() => {
    const actual = aNumero(texto)
    const equivalente = actual === null ? vacioEsCero && valor === 0 : actual === valor
    if (!equivalente) setTexto(String(valor))
    // Solo reacciona a cambios del valor externo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valor])

  const patron = decimales ? PATRON_DECIMAL : PATRON_ENTERO

  return (
    <input
      id={id}
      type="text"
      inputMode={decimales ? 'decimal' : 'numeric'}
      autoComplete="off"
      aria-label={ariaLabel}
      value={texto}
      onFocus={(evento) => evento.target.select()}
      onChange={(evento) => {
        const nuevo = evento.target.value.trim()
        if (!patron.test(nuevo)) return
        setTexto(nuevo)
        const numero = aNumero(nuevo)
        if (numero !== null) onCambiar(numero)
        else if (vacioEsCero) onCambiar(0)
      }}
      onBlur={() => {
        // Al salir, el campo muestra el valor que realmente quedó aplicado:
        // vacío no aplicado, o un número que el padre recortó a un rango
        // (p. ej. 99 con un máximo de 24 cuando ya estaba en 24, que no
        // cambia `valor` y por eso no dispara la sincronización de arriba).
        const actual = aNumero(texto)
        if (actual === null ? !vacioEsCero : actual !== valor) setTexto(String(valor))
      }}
      className={className}
    />
  )
}
