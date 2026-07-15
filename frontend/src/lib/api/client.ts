const EXTRACCION_BASE_URL = import.meta.env.VITE_EXTRACCION_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Todo pedido a `services/extraccion` pasa por acá.
 * `Accept: application/json` es lo que hace que el backend devuelva JSON en vez del HTML
 * legacy (ver `wants_json()` en services/extraccion/main.py) — sin este header, /procesar
 * responde con la página Jinja2 vieja en vez del payload que consume este frontend. */
export async function extraccionFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${EXTRACCION_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
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
