import { supabase } from '@/lib/supabase'

const PRESUPUESTACION_BASE_URL = import.meta.env.VITE_PRESUPUESTACION_API_URL ?? 'http://localhost:8001'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Todo pedido a `services/presupuestacion` pasa por acá. A diferencia de
 * `extraccionFetch`, este backend exige JWT real en todos sus routers
 * (`require_roles`/`get_current_user`), así que cada llamada inyecta el
 * `access_token` de la sesión actual de supabase-js. */
export async function presupuestacionFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  const response = await fetch(`${PRESUPUESTACION_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
      ...init?.headers,
    },
  })

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const message = body?.detail ?? `Error ${response.status} al llamar ${path}`
    throw new ApiError(message, response.status)
  }

  return body as T
}
