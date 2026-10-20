import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api/presupuestacion'
import { LoginForm } from './LoginForm'

const { signInMock } = vi.hoisted(() => ({ signInMock: vi.fn() }))

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: vi.fn() } } }))

vi.mock('./AuthContext', () => ({
  useAuth: () => ({ signIn: signInMock }),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

beforeEach(() => {
  signInMock.mockReset()
})

function completarFormulario(usuario = 'jperez') {
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: usuario } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'password123' } })
  fireEvent.submit(screen.getByRole('button', { name: /ingresar/i }).closest('form')!)
}

describe('LoginForm (S1: login con usuario)', () => {
  it('pide Usuario y contraseña, sin campo de email', () => {
    render(<LoginForm onSuccess={vi.fn()} />)
    expect(screen.getByLabelText('Usuario')).toHaveAttribute('type', 'text')
    expect(screen.queryByLabelText('Email')).toBeNull()
  })

  it('llama a signIn con el usuario y a onSuccess cuando resuelve', async () => {
    signInMock.mockResolvedValue(undefined)
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(signInMock).toHaveBeenCalledWith('jperez', 'password123')
  })

  it('un 401 muestra "Usuario o contraseña incorrectos" y no llama a onSuccess', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const errorReal = new ApiError('Usuario o contraseña incorrectos', 401)
    signInMock.mockRejectedValue(errorReal)
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    await waitFor(() => expect(screen.getByText('Usuario o contraseña incorrectos')).toBeInTheDocument())
    expect(onSuccess).not.toHaveBeenCalled()
    expect(consoleError).toHaveBeenCalledWith(expect.any(String), errorReal)
    consoleError.mockRestore()
  })

  it('un 429 muestra el mensaje de demasiados intentos del backend', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    signInMock.mockRejectedValue(
      new ApiError('Demasiados intentos. Probá de nuevo en unos minutos.', 429),
    )
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    expect(
      await screen.findByText('Demasiados intentos. Probá de nuevo en unos minutos.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Usuario o contraseña incorrectos')).toBeNull()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('un 503 muestra el mensaje de servicio no disponible del backend', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    signInMock.mockRejectedValue(
      new ApiError('El servicio de autenticación no está disponible. Probá de nuevo en unos minutos.', 503),
    )
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    expect(
      await screen.findByText('El servicio de autenticación no está disponible. Probá de nuevo en unos minutos.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Usuario o contraseña incorrectos')).toBeNull()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('un 500 sigue mostrando el mensaje genérico de reintento', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    signInMock.mockRejectedValue(new ApiError('boom', 500))
    render(<LoginForm onSuccess={vi.fn()} />)

    completarFormulario()

    expect(await screen.findByText('No pudimos iniciar sesión. Probá de nuevo.')).toBeInTheDocument()
  })

  it('reemplaza "¿Olvidaste tu contraseña?" por el aviso de contactar al administrador', () => {
    render(<LoginForm onSuccess={vi.fn()} />)
    expect(screen.queryByText('¿Olvidaste tu contraseña?')).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
    expect(
      screen.getByText('¿Olvidaste tu contraseña? Contactá al administrador para que te la blanquee.'),
    ).toBeInTheDocument()
  })
})
