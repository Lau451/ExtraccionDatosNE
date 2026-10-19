import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MiCuenta } from './MiCuenta'

const { navigateMock, signOutMock } = vi.hoisted(() => ({ navigateMock: vi.fn(), signOutMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}))

vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: vi.fn(), updateUser: vi.fn() } } }))

vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({
    perfil: {
      id: 'yo',
      rol: 'admin',
      nombre: 'Ana',
      apellido: 'Gómez',
      username: 'agomez',
      debe_cambiar_password: false,
    },
    session: { user: { id: 'yo', email: '3f2a@interno.local' } },
    signOut: signOutMock,
    refrescarPerfil: vi.fn(),
  }),
}))

beforeEach(() => {
  navigateMock.mockReset()
  signOutMock.mockReset().mockResolvedValue(undefined)
})

describe('MiCuenta', () => {
  it('ofrece cambiar la contraseña desde la pantalla de cambio (S3)', () => {
    render(<MiCuenta />)
    expect(screen.getByRole('link', { name: 'Cambiar contraseña' })).toHaveAttribute('href', '/cambiar-password')
  })

  it('muestra el nombre de usuario y nunca el email interno de auth (S1)', () => {
    render(<MiCuenta />)
    expect(screen.getByText('agomez')).toBeInTheDocument()
    expect(screen.queryByText(/interno\.local/)).toBeNull()
    expect(screen.queryByLabelText('Email nuevo')).toBeNull()
  })

  it('cerrar sesión sigue funcionando', async () => {
    render(<MiCuenta />)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: '/login' }))
    expect(signOutMock).toHaveBeenCalledTimes(1)
  })
})
