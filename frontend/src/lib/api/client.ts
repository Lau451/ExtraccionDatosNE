import { supabase } from '@/lib/supabase'

const EXTRACCION_BASE_URL = import.meta.env.VITE_EXTRACCION_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Todo pedido a `services/extraccion` pasa por acá. Igual que `presupuestacionFetch`,
 * inyecta el `access_token` de la sesión actual de supabase-js -- el backend exige JWT
 * real en todo endpoint no-legacy (extraccion-multi-tenant, T1). No se fija
 * `Content-Type` acá: para uploads con FormData el browser tiene que setear su propio
 * boundary, así que ni este objeto ni `init?.headers` deben forzarlo.
 * `Accept: application/json` es lo que hace que el backend devuelva JSON en vez del HTML
 * legacy (ver `wants_json()` en services/extraccion/main.py) — sin este header, /procesar
 * responde con la página Jinja2 vieja en vez del payload que consume este frontend. */
export async function extraccionFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  const response = await fetch(`${EXTRACCION_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
      ...init?.headers,
    },
  })

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const message = body?.error ?? `Error ${response.status} al llamar ${path}`
    throw new ApiError(message, response.status)
  }

  return body as T
}
