export function contarEntregas(cantidad: number): string {
  return `${cantidad} ${cantidad === 1 ? 'entrega' : 'entregas'}`
}
