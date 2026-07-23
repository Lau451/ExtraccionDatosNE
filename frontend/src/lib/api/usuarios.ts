import type { Rol } from '@/features/auth/AuthContext'
import { presupuestacionFetch } from './presupuestacion'

export interface Usuario {
  id: string
  drogueria_id: string | null
  // string, no Rol: la tabla admite también "sistema" (usuarios técnicos),
  // que no es un rol asignable desde esta UI.
  rol: string
  nombre: string
  apellido: string | null
  es_sistema: boolean
  activo: boolean
}

export interface ActualizarPerfilPayload {
  nombre?: string
  apellido?: string
}

export interface InvitarUsuarioPayload {
  email: string
  nombre: string
  apellido: string
  rol: Rol
  drogueria_id?: string
}

export function actualizarPerfilPropio(payload: ActualizarPerfilPayload) {
  return presupuestacionFetch('/usuarios/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listarUsuarios(): Promise<Usuario[]> {
  return presupuestacionFetch<Usuario[]>('/usuarios')
}

export function invitarUsuario(payload: InvitarUsuarioPayload): Promise<Usuario> {
  return presupuestacionFetch<Usuario>('/usuarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function cambiarRolUsuario(usuarioId: string, rol: string): Promise<Usuario> {
  return presupuestacionFetch<Usuario>(`/usuarios/${usuarioId}/rol`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rol }),
  })
}

export function cambiarActivoUsuario(usuarioId: string, activo: boolean): Promise<Usuario> {
  return presupuestacionFetch<Usuario>(`/usuarios/${usuarioId}/activo`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ activo }),
  })
}

export function eliminarUsuario(usuarioId: string): Promise<void> {
  return presupuestacionFetch<void>(`/usuarios/${usuarioId}`, { method: 'DELETE' })
}
