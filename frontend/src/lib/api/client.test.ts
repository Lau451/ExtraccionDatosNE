import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { getSessionMock } = vi.hoisted(() => ({ getSessionMock: vi.fn() }))
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: getSessionMock } } }))

import { ApiError, extraccionFetch } from './client'

function mockFetchOnce(body: unknown, init?: { status?: number; ok?: boolean }) {
  const status = init?.status ?? 200
  const ok = init?.ok ?? (status >= 200 && status < 300)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      status,
      json: () => Promise.resolve(body),
    }),
  )
}

describe('extraccionFetch', () => {
  beforeEach(() => {
    getSessionMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('adjunta el Authorization: Bearer con el access_token de la sesión actual', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: { access_token: 'token-de-prueba' } },
    })
    mockFetchOnce({ documentos: [] })

    await extraccionFetch('/api/documentos')

    const [, init] = vi.mocked(fetch).mock.calls[0]
    const headers = init?.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer token-de-prueba')
    expect(headers.Accept).toBe('application/json')
  })

  it('sin sesión activa, no manda header Authorization (el backend responde 401)', async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } })
    mockFetchOnce({ detail: 'no autenticado' }, { status: 401, ok: false })

    await expect(extraccionFetch('/api/documentos')).rejects.toBeInstanceOf(ApiError)

    const [, init] = vi.mocked(fetch).mock.calls[0]
    const headers = init?.headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it('en un upload multipart no fuerza Content-Type (FormData necesita su propio boundary)', async () => {
    getSessionMock.mockResolvedValue({
      data: { session: { access_token: 'token-de-prueba' } },
    })
    mockFetchOnce({ ok: true, tipo: '' })

    const formData = new FormData()
    formData.append('archivo', new Blob(['contenido']), 'doc.pdf')

    await extraccionFetch('/procesar', { method: 'POST', body: formData })

    const [, init] = vi.mocked(fetch).mock.calls[0]
    const headers = init?.headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
    expect(init?.body).toBe(formData)
  })
})
