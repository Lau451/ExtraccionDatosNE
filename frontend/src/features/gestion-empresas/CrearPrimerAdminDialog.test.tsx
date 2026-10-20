import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CrearPrimerAdminDialog } from './CrearPrimerAdminDialog'

vi.mock('@/lib/api/usuarios', () => ({
  crearUsuario: vi.fn(),
}))

import { ApiError } from '@/lib/api/presupuestacion'
import { crearUsuario } from '@/lib/api/usuarios'

function abrirDialogo() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <CrearPrimerAdminDialog drogueriaId="drog-1" drogueriaNombre="Droguería Uno" />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Crear admin' }))
  return within(screen.getByRole('dialog'))
}

function completar(dialogo: ReturnType<typeof within>, username: string, password: string) {
  fireEvent.change(dialogo.getByLabelText('Usuario'), { target: { value: username } })
  fireEvent.change(dialogo.getByLabelText('Contraseña temporal'), { target: { value: password } })
  fireEvent.change(dialogo.getByLabelText('Nombre'), { target: { value: 'Ana' } })
  fireEvent.change(dialogo.getByLabelText('Apellido'), { target: { value: 'Gómez' } })
  fireEvent.click(dialogo.getByRole('button', { name: 'Crear' }))
}

describe('CrearPrimerAdminDialog', () => {
  beforeEach(() => {
    vi.mocked(crearUsuario).mockReset()
  })

  it('pide usuario y contraseña temporal, no email', () => {
    const dialogo = abrirDialogo()
    expect(dialogo.queryByLabelText('Email')).toBeNull()
    expect(
      dialogo.getByText(
        'Pasale al usuario su nombre de usuario y la contraseña temporal. Se le va a pedir que la cambie en el primer ingreso.',
      ),
    ).toBeInTheDocument()
  })

  it('crea el admin de la droguería con username en minúsculas y contraseña temporal', async () => {
    vi.mocked(crearUsuario).mockResolvedValue({} as never)
    const dialogo = abrirDialogo()
    completar(dialogo, 'AGomez', 'temporal1')

    await waitFor(() =>
      expect(crearUsuario).toHaveBeenCalledWith({
        username: 'agomez',
        password: 'temporal1',
        nombre: 'Ana',
        apellido: 'Gómez',
        rol: 'admin',
        drogueria_id: 'drog-1',
      }),
    )
  })

  it('rechaza un username inválido sin llamar al backend', () => {
    const dialogo = abrirDialogo()
    completar(dialogo, 'ag', 'temporal1')
    expect(
      dialogo.getByText(
        'El nombre de usuario debe tener entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo',
      ),
    ).toBeInTheDocument()
    expect(crearUsuario).not.toHaveBeenCalled()
  })

  it('rechaza una contraseña temporal de 7 caracteres sin llamar al backend', () => {
    const dialogo = abrirDialogo()
    completar(dialogo, 'agomez', 'tempor1')
    expect(dialogo.getByText('La contraseña temporal debe tener al menos 8 caracteres.')).toBeInTheDocument()
    expect(crearUsuario).not.toHaveBeenCalled()
  })

  it('muestra el error del backend (usuario duplicado)', async () => {
    vi.mocked(crearUsuario).mockRejectedValue(new ApiError('Ya existe un usuario con ese nombre de usuario', 409))
    const dialogo = abrirDialogo()
    completar(dialogo, 'agomez', 'temporal1')
    expect(await dialogo.findByText('Ya existe un usuario con ese nombre de usuario')).toBeInTheDocument()
  })
})
