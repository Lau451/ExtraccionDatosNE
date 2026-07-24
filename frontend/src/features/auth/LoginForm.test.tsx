import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginForm } from './LoginForm'

const { signInMock } = vi.hoisted(() => ({ signInMock: vi.fn() }))

vi.mock('./AuthContext', () => ({
  useAuth: () => ({ signIn: signInMock }),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

beforeEach(() => {
  signInMock.mockReset()
})

function completarFormulario() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@test.com' } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'password123' } })
  fireEvent.submit(screen.getByRole('button', { name: /ingresar/i }).closest('form')!)
}

describe('LoginForm', () => {
  it('llama a onSuccess cuando signIn resuelve', async () => {
    signInMock.mockResolvedValue(undefined)
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(signInMock).toHaveBeenCalledWith('user@test.com', 'password123')
  })

  it('muestra el mensaje genérico y no llama a onSuccess si signIn falla', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const errorReal = new Error('Invalid login credentials')
    signInMock.mockRejectedValue(errorReal)
    const onSuccess = vi.fn()
    render(<LoginForm onSuccess={onSuccess} />)

    completarFormulario()

    await waitFor(() => expect(screen.getByText('Email o contraseña incorrectos')).toBeInTheDocument())
    expect(onSuccess).not.toHaveBeenCalled()
    expect(consoleError).toHaveBeenCalledWith(expect.any(String), errorReal)
    consoleError.mockRestore()
  })
})
