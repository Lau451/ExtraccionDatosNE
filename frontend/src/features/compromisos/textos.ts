export function contarEntregas(cantidad: number): string {
  return `${cantidad} ${cantidad === 1 ? 'entrega' : 'entregas'}`
}

export function contarRenglones(cantidad: number): string {
  return `${cantidad} ${cantidad === 1 ? 'renglón' : 'renglones'}`
}
