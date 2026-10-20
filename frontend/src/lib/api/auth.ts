import { ApiError, PRESUPUESTACION_BASE_URL, presupuestacionFetch } from './presupuestacion'

/** Campos de sesión de Supabase que devuelve `POST /auth/login` — el backend
 * resuelve el username al email interno de auth y hace el login del lado del
 * servidor, así ese email nunca llega al navegador (spec S1). */
export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  // Backend `LoginOut.expires_at` is `int | None` (spec S11).
  expires_at: number | null
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
    // Without a backend `detail` (e.g. a proxy 503/429 with an HTML body) the login
    // screen shows a friendly retry text instead of "Error N" (spec S12).
    const message = typeof body?.detail === 'string' ? body.detail : 'No pudimos iniciar sesión. Probá de nuevo.'
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
