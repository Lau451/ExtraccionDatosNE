import { presupuestacionFetch } from './presupuestacion'

export interface Drogueria {
  id: string
  nombre: string
  razon_social: string
  cuit: string
  ciudad: string
  provincia: string
  codigo_postal: string | null
  contacto_email: string
  contacto_telefono: string
  activa: boolean
  plan_id: string | null
}

export interface DrogueriaCreatePayload {
  nombre: string
  razon_social: string
  cuit: string
  ciudad: string
  provincia: string
  codigo_postal?: string
  contacto_email: string
  contacto_telefono: string
}

export interface DrogueriaUpdatePayload {
  nombre?: string
  razon_social?: string
  cuit?: string
  ciudad?: string
  provincia?: string
  codigo_postal?: string
  contacto_email?: string
  contacto_telefono?: string
  activa?: boolean
  plan_id?: string | null
}

export function listarDroguerias(): Promise<Drogueria[]> {
  return presupuestacionFetch<Drogueria[]>('/droguerias')
}

export function crearDrogueria(payload: DrogueriaCreatePayload): Promise<Drogueria> {
  return presupuestacionFetch<Drogueria>('/droguerias', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarDrogueria(
  drogueriaId: string,
  payload: DrogueriaUpdatePayload,
): Promise<Drogueria> {
  return presupuestacionFetch<Drogueria>(`/droguerias/${drogueriaId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function eliminarDrogueria(drogueriaId: string): Promise<void> {
  return presupuestacionFetch<void>(`/droguerias/${drogueriaId}`, { method: 'DELETE' })
}
