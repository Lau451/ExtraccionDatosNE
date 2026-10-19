import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api/presupuestacion'
import { CambiarPasswordPage } from './CambiarPasswordPage'

const { authMock } = vi.hoisted(() => ({
  authMock: {
    perfil: { id: 'yo', rol: 'compras', debe_cambiar_password: true } as {
      id: string
      rol: string
      debe_cambiar_password: boolean
    },
    refrescarPerfil: vi.fn(),
    signOut: vi.fn(),
  },
}))

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: vi.fn() } } }))
vi.mock('@/lib/api/auth', () => ({ cambiarPasswordPropia: vi.fn() }))
vi.mock('./AuthContext', () => ({ useAuth: () => authMock }))

import { cambiarPasswordPropia } from '@/lib/api/auth'

const irA = vi.fn()

beforeEach(() => {
  irA.mockReset()
  authMock.refrescarPerfil.mockReset().mockResolvedValue(undefined)
  authMock.signOut.mockReset().mockResolvedValue(undefined)
  authMock.perfil = { id: 'yo', rol: 'compras', debe_cambiar_password: true }
  vi.mocked(cambiarPasswordPropia).mockReset()
})

function llenarYEnviar(actual: string, nueva: string, confirmacion: string) {
  fireEvent.change(screen.getByLabelText('Contraseña actual'), { target: { value: actual } })
  fireEvent.change(screen.getByLabelText('Contraseña nueva'), { target: { value: nueva } })
  fireEvent.change(screen.getByLabelText('Repetir contraseña nueva'), { target: { value: confirmacion } })
  fireEvent.submit(screen.getByRole('button', { name: 'Cambiar contraseña' }).closest('form')!)
}

describe('CambiarPasswordPage (S3)', () => {
  it('rechaza una contraseña nueva de menos de 8 caracteres sin llamar al backend', async () => {
    render(<CambiarPasswordPage irA={irA} />)
    llenarYEnviar('temporal1', 'corta1', 'corta1')

    expect(await screen.findByText('La contraseña nueva debe tener al menos 8 caracteres')).toBeInTheDocument()
    expect(cambiarPasswordPropia).not.toHaveBeenCalled()
  })

  it('rechaza una contraseña nueva igual a la actual', async () => {
    render(<CambiarPasswordPage irA={irA} />)
    llenarYEnviar('temporal1', 'temporal1', 'temporal1')

    expect(await screen.findByText('La contraseña nueva tiene que ser distinta de la actual')).toBeInTheDocument()
    expect(cambiarPasswordPropia).not.toHaveBeenCalled()
  })

  it('rechaza si la confirmación no coincide', async () => {
    render(<CambiarPasswordPage irA={irA} />)
    llenarYEnviar('temporal1', 'nueva12345', 'otra123456')

    expect(await screen.findByText('Las contraseñas no coinciden')).toBeInTheDocument()
    expect(cambiarPasswordPropia).not.toHaveBeenCalled()
  })

  it('con el flag activo avisa que la contraseña es temporal y no ofrece cancelar', () => {
    render(<CambiarPasswordPage irA={irA} />)
    expect(screen.getByText('Tu contraseña es temporal. Tenés que cambiarla antes de continuar.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()
  })

  it('al cambiarla llama al backend, refresca el perfil y va al aterrizaje del rol', async () => {
    vi.mocked(cambiarPasswordPropia).mockResolvedValue(undefined)
    render(<CambiarPasswordPage irA={irA} />)
    llenarYEnviar('temporal1', 'nueva12345', 'nueva12345')

    await waitFor(() => expect(irA).toHaveBeenCalledWith('/productos'))
    expect(cambiarPasswordPropia).toHaveBeenCalledWith({ password_actual: 'temporal1', password_nueva: 'nueva12345' })
    expect(authMock.refrescarPerfil).toHaveBeenCalledTimes(1)
  })

  it('muestra el error del backend (ej. contraseña actual incorrecta) y no navega', async () => {
    vi.mocked(cambiarPasswordPropia).mockRejectedValue(new ApiError('La contraseña actual es incorrecta', 400))
    render(<CambiarPasswordPage irA={irA} />)
    llenarYEnviar('mala12345', 'nueva12345', 'nueva12345')

    expect(await screen.findByText('La contraseña actual es incorrecta')).toBeInTheDocument()
    expect(irA).not.toHaveBeenCalled()
    expect(authMock.refrescarPerfil).not.toHaveBeenCalled()
  })

  it('cambio voluntario: ofrece cancelar y vuelve a Mi cuenta', () => {
    authMock.perfil = { id: 'yo', rol: 'admin', debe_cambiar_password: false }
    render(<CambiarPasswordPage irA={irA} />)
    expect(screen.queryByText('Tu contraseña es temporal. Tenés que cambiarla antes de continuar.')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(irA).toHaveBeenCalledWith('/mi-cuenta')
  })

  it('cerrar sesión sigue disponible desde la pantalla de cambio', async () => {
    render(<CambiarPasswordPage irA={irA} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))

    await waitFor(() => expect(irA).toHaveBeenCalledWith('/login'))
    expect(authMock.signOut).toHaveBeenCalledTimes(1)
  })
})
