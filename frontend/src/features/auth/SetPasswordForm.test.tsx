import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SetPasswordForm } from './SetPasswordForm'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      updateUser: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

import { supabase } from '@/lib/supabase'

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(supabase.auth.updateUser).mockReset()
  vi.mocked(supabase.auth.signOut).mockReset()
})

function llenarYEnviar(password: string, confirmacion: string) {
  fireEvent.change(screen.getByLabelText('Contraseña nueva'), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('Repetir contraseña'), { target: { value: confirmacion } })
  fireEvent.submit(screen.getByRole('button', { name: /guardar contraseña/i }).closest('form')!)
}

describe('SetPasswordForm', () => {
  it('bloquea el submit si las contraseñas no coinciden', async () => {
    render(<SetPasswordForm title="t" />)
    llenarYEnviar('password123', 'otraCosa123')

    await waitFor(() => expect(screen.getByText('Las contraseñas no coinciden')).toBeInTheDocument())
    expect(supabase.auth.updateUser).not.toHaveBeenCalled()
  })

  it('bloquea el submit si la contraseña no tiene ningún número', async () => {
    render(<SetPasswordForm title="t" />)
    llenarYEnviar('sololetras', 'sololetras')

    await waitFor(() =>
      expect(
        screen.getByText('La contraseña debe tener al menos una letra y un número'),
      ).toBeInTheDocument(),
    )
    expect(supabase.auth.updateUser).not.toHaveBeenCalled()
  })

  it('guarda, cierra sesión y navega a /login si la contraseña es válida', async () => {
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({ error: null } as never)
    vi.mocked(supabase.auth.signOut).mockResolvedValue({ error: null } as never)
    render(<SetPasswordForm title="t" />)
    llenarYEnviar('password123', 'password123')

    await waitFor(() =>
      expect(supabase.auth.updateUser).toHaveBeenCalledWith({ password: 'password123' }),
    )
    expect(supabase.auth.signOut).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith({ to: '/login' })
  })
})
