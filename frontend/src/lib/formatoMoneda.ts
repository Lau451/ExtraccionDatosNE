const formato = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Formato único de montos en pesos: prefijo "$ " (con espacio), miles con '.' y
// decimales con ',' (p. ej. "$ 1.234,50").
export function formatearMoneda(monto: number): string {
  return `$ ${formato.format(monto)}`
}
