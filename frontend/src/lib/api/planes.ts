import { presupuestacionFetch } from './presupuestacion'

export interface Plan {
  id: string
  nombre: string
  max_usuarios: number | null
  max_documentos_mes: number | null
  almacenamiento_mb: number | null
  funcionalidades: Record<string, unknown>
  activo: boolean
}

export function listarPlanes(): Promise<Plan[]> {
  return presupuestacionFetch<Plan[]>('/planes')
}
