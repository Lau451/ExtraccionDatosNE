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
  username: string
  debe_cambiar_password: boolean
}

export interface ActualizarPerfilPayload {
  nombre?: string
  apellido?: string
}

/** Alta por el admin (spec S2): username + contraseña temporal, sin email ni
 * invitación. El usuario la tiene que cambiar en el primer ingreso (S3). */
export interface CrearUsuarioPayload {
  username: string
  password: string
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

export function crearUsuario(payload: CrearUsuarioPayload): Promise<Usuario> {
  return presupuestacionFetch<Usuario>('/usuarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** Blanqueo (spec S4): contraseña temporal nueva + `debe_cambiar_password`. */
export function blanquearPasswordUsuario(usuarioId: string, password: string): Promise<Usuario> {
  return presupuestacionFetch<Usuario>(`/usuarios/${usuarioId}/password`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function cambiarUsernameUsuario(usuarioId: string, username: string): Promise<Usuario> {
  return presupuestacionFetch<Usuario>(`/usuarios/${usuarioId}/username`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
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
