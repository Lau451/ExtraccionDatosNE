import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      // Una sesión vieja en el storage no tiene que viajar al login público.
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: 'token-viejo' } } }),
    },
  },
}))

import { cambiarPasswordPropia, iniciarSesion } from './auth'
import { ApiError } from './presupuestacion'

const fetchMock = vi.fn()

function respuesta(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('iniciarSesion (S1)', () => {
  it('hace POST /auth/login con username y password, sin Authorization', async () => {
    const sesion = {
      access_token: 'a',
      refresh_token: 'r',
      expires_in: 3600,
      expires_at: 123,
      token_type: 'bearer',
      user: { id: 'user-1' },
    }
    fetchMock.mockResolvedValue(respuesta(200, sesion))

    await expect(iniciarSesion('jperez', 'secreta123')).resolves.toEqual(sesion)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/auth\/login$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ username: 'jperez', password: 'secreta123' })
    expect(init.headers).not.toHaveProperty('Authorization')
  })

  it('rechaza con ApiError 401 y el mensaje del backend', async () => {
    fetchMock.mockResolvedValue(respuesta(401, { detail: 'Usuario o contraseña incorrectos' }))

    const error = await iniciarSesion('nadie', 'x').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(401)
    expect(error.message).toBe('Usuario o contraseña incorrectos')
  })
})

describe('iniciarSesion sin detail del backend (S12)', () => {
  it.each([503, 429])('un %i sin JSON (proxy) da el texto genérico de reintento, no "Error N"', async (status) => {
    fetchMock.mockResolvedValue({ ok: false, status, json: () => Promise.reject(new SyntaxError('no json')) })

    const error = await iniciarSesion('jperez', 'password123').catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(status)
    expect((error as ApiError).message).toBe('No pudimos iniciar sesión. Probá de nuevo.')
  })
})

describe('cambiarPasswordPropia (S3)', () => {
  it('hace POST /auth/cambiar-password autenticado con password_actual y password_nueva', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject(new Error('sin body')) })

    await cambiarPasswordPropia({ password_actual: 'temporal1', password_nueva: 'nueva1234' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/auth\/cambiar-password$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ password_actual: 'temporal1', password_nueva: 'nueva1234' })
    expect(init.headers.Authorization).toBe('Bearer token-viejo')
  })
})
