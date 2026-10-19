import { ApiError, PRESUPUESTACION_BASE_URL, presupuestacionFetch } from './presupuestacion'

/** Campos de sesión de Supabase que devuelve `POST /auth/login` — el backend
 * resuelve el username al email interno de auth y hace el login del lado del
 * servidor, así ese email nunca llega al navegador (spec S1). */
export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  expires_at: number
  token_type: string
  user: { id: string }
}

export interface CambiarPasswordPayload {
  password_actual: string
  password_nueva: string
}

/** Endpoint público: no pasa por `presupuestacionFetch` a propósito, para no
 * mandar el `Authorization` de una sesión vieja que pudiera quedar en storage. */
export async function iniciarSesion(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${PRESUPUESTACION_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const message = typeof body?.detail === 'string' ? body.detail : `Error ${response.status} al iniciar sesión`
    throw new ApiError(message, response.status)
  }

  return body as LoginResponse
}

export function cambiarPasswordPropia(payload: CambiarPasswordPayload): Promise<void> {
  return presupuestacionFetch<void>('/auth/cambiar-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
