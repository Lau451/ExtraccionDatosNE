import type { EstadoMatching, RenglonMatching } from '@/lib/api/matching'

const ESTADOS_RESUELTOS: EstadoMatching[] = ['automatico', 'confirmado', 'sin_match']

export const ESTILO_ESTADO: Record<EstadoMatching, string> = {
  pendiente: 'bg-amber-50 text-amber-800 ring-amber-200',
  sugerido: 'bg-sky-50 text-sky-800 ring-sky-200',
  automatico: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  confirmado: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  sin_match: 'bg-slate-100 text-slate-700 ring-slate-200',
}

export function estaResuelto(renglon: RenglonMatching): boolean {
  return ESTADOS_RESUELTOS.includes(renglon.estado_matching)
}

export function porcentaje(confianza: string): string {
  return `${Math.round(Number(confianza))}%`
}

export function etiquetaEstado(renglon: RenglonMatching): string {
  switch (renglon.estado_matching) {
    case 'pendiente':
      return 'Pendiente'
    case 'sugerido':
      return renglon.confianza_matching ? `Sugerido ${porcentaje(renglon.confianza_matching)}` : 'Sugerido'
    case 'automatico':
      return 'Automático'
    case 'confirmado':
      return 'Confirmado'
    case 'sin_match':
      return 'Sin match'
  }
}

export function formatearCantidad(cantidad: string): string {
  return Number(cantidad).toLocaleString('es-AR', { maximumFractionDigits: 2 })
}
