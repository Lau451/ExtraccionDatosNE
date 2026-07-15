import { presupuestacionFetch } from './presupuestacion'

export type Clase = 'cotizacion' | 'licitacion'
export type Modalidad = 'mail' | 'pliego'

export interface ProcesoComercialResumen {
  id: string
  nombre: string
  clase: Clase
  estado: string
}

export interface ProcesoComercialCreatePayload {
  nombre: string
  clase: Clase
  cliente_id?: string
  apertura?: string
  modalidad?: Modalidad
}

export function listarProcesosComerciales(): Promise<ProcesoComercialResumen[]> {
  return presupuestacionFetch<ProcesoComercialResumen[]>('/procesos-comerciales')
}

export function crearProcesoComercial(
  payload: ProcesoComercialCreatePayload,
): Promise<ProcesoComercialResumen> {
  return presupuestacionFetch<ProcesoComercialResumen>('/procesos-comerciales', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
