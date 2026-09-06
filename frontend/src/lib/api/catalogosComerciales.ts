import { presupuestacionFetch } from './presupuestacion'

export type TipoFormaPago = 'transferencia' | 'cheque' | 'echeq' | 'efectivo' | 'deposito' | 'otro'

export interface SectorContacto {
  id: string
  drogueria_id: string
  nombre: string
  descripcion: string | null
  activo: boolean
}

export interface SectorContactoCreatePayload {
  nombre: string
  descripcion?: string
}

export interface SectorContactoUpdatePayload {
  nombre?: string
  descripcion?: string
  activo?: boolean
}

export interface CondicionPago {
  id: string
  drogueria_id: string
  nombre: string
  plazos_dias: number[]
  descripcion: string | null
  activo: boolean
}

export interface CondicionPagoCreatePayload {
  nombre: string
  plazos_dias?: number[]
  descripcion?: string
}

export interface CondicionPagoUpdatePayload {
  nombre?: string
  plazos_dias?: number[]
  descripcion?: string
  activo?: boolean
}

export interface FormaPago {
  id: string
  drogueria_id: string
  nombre: string
  tipo: TipoFormaPago
  descripcion: string | null
  activo: boolean
}

export interface FormaPagoCreatePayload {
  nombre: string
  tipo?: TipoFormaPago
  descripcion?: string
}

export interface FormaPagoUpdatePayload {
  nombre?: string
  tipo?: TipoFormaPago
  descripcion?: string
  activo?: boolean
}

// Sectores de contacto

export function listarSectoresContacto(): Promise<SectorContacto[]> {
  return presupuestacionFetch<SectorContacto[]>('/sectores-contacto')
}

export function crearSectorContacto(
  payload: SectorContactoCreatePayload,
): Promise<SectorContacto> {
  return presupuestacionFetch<SectorContacto>('/sectores-contacto', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarSectorContacto(
  sectorId: string,
  payload: SectorContactoUpdatePayload,
): Promise<SectorContacto> {
  return presupuestacionFetch<SectorContacto>(`/sectores-contacto/${sectorId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Condiciones de pago

export function listarCondicionesPago(): Promise<CondicionPago[]> {
  return presupuestacionFetch<CondicionPago[]>('/condiciones-pago')
}

export function crearCondicionPago(
  payload: CondicionPagoCreatePayload,
): Promise<CondicionPago> {
  return presupuestacionFetch<CondicionPago>('/condiciones-pago', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarCondicionPago(
  condicionId: string,
  payload: CondicionPagoUpdatePayload,
): Promise<CondicionPago> {
  return presupuestacionFetch<CondicionPago>(`/condiciones-pago/${condicionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Formas de pago

export function listarFormasPago(): Promise<FormaPago[]> {
  return presupuestacionFetch<FormaPago[]>('/formas-pago')
}

export function crearFormaPago(payload: FormaPagoCreatePayload): Promise<FormaPago> {
  return presupuestacionFetch<FormaPago>('/formas-pago', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function actualizarFormaPago(
  formaId: string,
  payload: FormaPagoUpdatePayload,
): Promise<FormaPago> {
  return presupuestacionFetch<FormaPago>(`/formas-pago/${formaId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
