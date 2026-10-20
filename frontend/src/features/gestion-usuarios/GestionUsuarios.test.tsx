import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GestionUsuarios } from './GestionUsuarios'

const { perfilMock } = vi.hoisted(() => ({
  perfilMock: { id: 'yo', rol: 'gerencia' as string },
}))

vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: perfilMock }),
}))

vi.mock('@/lib/api/droguerias', () => ({ listarDroguerias: vi.fn().mockResolvedValue([]) }))

vi.mock('@/lib/api/usuarios', () => ({
  listarUsuarios: vi.fn(),
  cambiarActivoUsuario: vi.fn(),
  cambiarRolUsuario: vi.fn(),
  eliminarUsuario: vi.fn(),
  crearUsuario: vi.fn(),
  blanquearPasswordUsuario: vi.fn(),
  cambiarUsernameUsuario: vi.fn(),
}))

import { ApiError } from '@/lib/api/presupuestacion'
import {
  blanquearPasswordUsuario,
  cambiarActivoUsuario,
  cambiarRolUsuario,
  cambiarUsernameUsuario,
  crearUsuario,
  listarUsuarios,
  type Usuario,
} from '@/lib/api/usuarios'

function usuario(id: string, rol: string): Usuario {
  return {
    id,
    drogueria_id: 'drog-1',
    rol,
    nombre: id,
    apellido: null,
    es_sistema: false,
    activo: true,
    username: id.toLowerCase(),
    debe_cambiar_password: false,
  }
}

function renderPantalla() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GestionUsuarios />
    </QueryClientProvider>,
  )
}

async function fila(nombre: string) {
  return within((await screen.findByText(nombre)).closest('tr')!)
}

function opcionesDe(select: HTMLElement) {
  return within(select)
    .getAllByRole('option')
    .map((o) => o.getAttribute('value'))
}

describe('GestionUsuarios (S7)', () => {
  beforeEach(() => {
    vi.mocked(listarUsuarios).mockResolvedValue([usuario('Ana', 'admin'), usuario('Beto', 'comercial')])
  })

  it('gerencia no puede editar filas de admin', async () => {
    perfilMock.rol = 'gerencia'
    renderPantalla()
    const filaAdmin = await fila('Ana')
    expect(filaAdmin.queryByRole('combobox')).toBeNull()
    expect(filaAdmin.queryByRole('button', { name: 'Desactivar' })).toBeNull()
    expect(filaAdmin.queryByRole('button', { name: 'Eliminar' })).toBeNull()
  })

  it('gerencia gestiona roles inferiores y no puede asignar admin (fila y alta)', async () => {
    perfilMock.rol = 'gerencia'
    renderPantalla()
    const filaComercial = await fila('Beto')
    expect(opcionesDe(filaComercial.getByRole('combobox'))).toEqual(['gerencia', 'lider_comercial', 'comercial', 'compras'])
    expect(filaComercial.getByRole('button', { name: 'Desactivar' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '+ Crear usuario' }))
    const dialogo = within(await screen.findByRole('dialog'))
    expect(opcionesDe(dialogo.getByRole('combobox'))).toEqual(['gerencia', 'lider_comercial', 'comercial', 'compras'])
  })

  it('admin sigue pudiendo editar la fila de otro admin, sin poder asignar admin', async () => {
    perfilMock.rol = 'admin'
    renderPantalla()
    const filaAdmin = await fila('Ana')
    expect(opcionesDe(filaAdmin.getByRole('combobox'))).toEqual(['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])
    expect(filaAdmin.getByRole('button', { name: 'Desactivar' })).toBeTruthy()
    expect(opcionesDe((await fila('Beto')).getByRole('combobox'))).not.toContain('admin')
  })

  it('superadmin sigue pudiendo asignar admin', async () => {
    perfilMock.rol = 'superadmin'
    renderPantalla()
    expect(opcionesDe((await fila('Beto')).getByRole('combobox'))).toContain('admin')
  })
})

async function abrirAlta() {
  fireEvent.click(await screen.findByRole('button', { name: '+ Crear usuario' }))
  return within(await screen.findByRole('dialog'))
}

function completarAlta(dialogo: ReturnType<typeof within>, username: string, password: string) {
  fireEvent.change(dialogo.getByLabelText('Usuario'), { target: { value: username } })
  fireEvent.change(dialogo.getByLabelText('Contraseña temporal'), { target: { value: password } })
  fireEvent.change(dialogo.getByLabelText('Nombre'), { target: { value: 'Juan' } })
  fireEvent.change(dialogo.getByLabelText('Apellido'), { target: { value: 'Pérez' } })
  fireEvent.submit(dialogo.getByRole('button', { name: 'Crear' }).closest('form')!)
}

const ERROR_USERNAME =
  'El nombre de usuario debe tener entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo'
const ERROR_TEMPORAL = 'La contraseña temporal debe tener al menos 8 caracteres.'
const DUPLICADO = 'Ya existe un usuario con ese nombre de usuario'

describe('GestionUsuarios: alta con usuario y contraseña temporal (S2)', () => {
  beforeEach(() => {
    perfilMock.rol = 'gerencia'
    vi.mocked(listarUsuarios).mockResolvedValue([usuario('Ana', 'admin'), usuario('Beto', 'comercial')])
    vi.mocked(crearUsuario).mockReset()
  })

  it('la lista muestra la columna Usuario con el username', async () => {
    renderPantalla()
    expect(await screen.findByRole('columnheader', { name: 'Usuario' })).toBeInTheDocument()
    expect((await fila('Beto')).getByText('beto')).toBeInTheDocument()
  })

  it('explica que hay que pasarle usuario y contraseña temporal y no pide email', async () => {
    renderPantalla()
    const dialogo = await abrirAlta()
    expect(
      dialogo.getByText(
        'Pasale al usuario su nombre de usuario y la contraseña temporal. Se le va a pedir que la cambie en el primer ingreso.',
      ),
    ).toBeInTheDocument()
    expect(dialogo.queryByLabelText('Email')).toBeNull()
  })

  it('crea el usuario con username en minúsculas y contraseña temporal', async () => {
    vi.mocked(crearUsuario).mockResolvedValue(usuario('Juan', 'gerencia'))
    renderPantalla()
    const dialogo = await abrirAlta()
    completarAlta(dialogo, 'JPerez', 'temporal1')

    await waitFor(() =>
      expect(crearUsuario).toHaveBeenCalledWith({
        username: 'jperez',
        password: 'temporal1',
        nombre: 'Juan',
        apellido: 'Pérez',
        rol: 'gerencia',
      }),
    )
  })

  it.each(['jp', 'a'.repeat(31), 'juan perez', 'juan@perez'])('rechaza el username inválido %s', async (username) => {
    renderPantalla()
    const dialogo = await abrirAlta()
    completarAlta(dialogo, username, 'temporal1')

    expect(await dialogo.findByText(ERROR_USERNAME)).toBeInTheDocument()
    expect(crearUsuario).not.toHaveBeenCalled()
  })

  it('rechaza una contraseña temporal de menos de 8 caracteres', async () => {
    renderPantalla()
    const dialogo = await abrirAlta()
    completarAlta(dialogo, 'jperez', 'corta1')

    expect(await dialogo.findByText(ERROR_TEMPORAL)).toBeInTheDocument()
    expect(crearUsuario).not.toHaveBeenCalled()
  })

  it('muestra el mensaje del backend ante un username duplicado (409)', async () => {
    vi.mocked(crearUsuario).mockRejectedValue(new ApiError(DUPLICADO, 409))
    renderPantalla()
    const dialogo = await abrirAlta()
    completarAlta(dialogo, 'jperez', 'temporal1')

    expect(await dialogo.findByText(DUPLICADO)).toBeInTheDocument()
  })
})

describe('GestionUsuarios: blanquear contraseña y editar usuario (S4/S5)', () => {
  beforeEach(() => {
    perfilMock.rol = 'gerencia'
    perfilMock.id = 'Yo'
    vi.mocked(listarUsuarios).mockResolvedValue([
      usuario('Ana', 'admin'),
      usuario('Beto', 'comercial'),
      usuario('Yo', 'gerencia'),
    ])
    vi.mocked(blanquearPasswordUsuario).mockReset()
    vi.mocked(cambiarUsernameUsuario).mockReset()
  })

  it('las acciones siguen la visibilidad de activar/desactivar', async () => {
    renderPantalla()
    const filaComercial = await fila('Beto')
    expect(filaComercial.getByRole('button', { name: 'Blanquear contraseña' })).toBeInTheDocument()
    expect(filaComercial.getByRole('button', { name: 'Editar usuario' })).toBeInTheDocument()

    for (const nombre of ['Ana', 'Yo']) {
      const f = await fila(nombre)
      expect(f.queryByRole('button', { name: 'Desactivar' })).toBeNull()
      expect(f.queryByRole('button', { name: 'Blanquear contraseña' })).toBeNull()
      expect(f.queryByRole('button', { name: 'Editar usuario' })).toBeNull()
    }
  })

  it('blanquea la contraseña con una temporal nueva', async () => {
    vi.mocked(blanquearPasswordUsuario).mockResolvedValue(usuario('Beto', 'comercial'))
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Blanquear contraseña' }))
    const dialogo = within(await screen.findByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText('Contraseña temporal nueva'), { target: { value: 'temporal99' } })
    fireEvent.submit(dialogo.getByRole('button', { name: 'Blanquear' }).closest('form')!)

    await waitFor(() => expect(blanquearPasswordUsuario).toHaveBeenCalledWith('Beto', 'temporal99'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('no blanquea con una temporal de menos de 8 caracteres', async () => {
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Blanquear contraseña' }))
    const dialogo = within(await screen.findByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText('Contraseña temporal nueva'), { target: { value: 'corta' } })
    fireEvent.submit(dialogo.getByRole('button', { name: 'Blanquear' }).closest('form')!)

    expect(await dialogo.findByText(ERROR_TEMPORAL)).toBeInTheDocument()
    expect(blanquearPasswordUsuario).not.toHaveBeenCalled()
  })

  it('edita el username (en minúsculas) partiendo del actual', async () => {
    vi.mocked(cambiarUsernameUsuario).mockResolvedValue(usuario('Beto', 'comercial'))
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Editar usuario' }))
    const dialogo = within(await screen.findByRole('dialog'))
    expect(dialogo.getByLabelText('Usuario')).toHaveValue('beto')
    fireEvent.change(dialogo.getByLabelText('Usuario'), { target: { value: 'Beto.Nuevo' } })
    fireEvent.submit(dialogo.getByRole('button', { name: 'Guardar' }).closest('form')!)

    await waitFor(() => expect(cambiarUsernameUsuario).toHaveBeenCalledWith('Beto', 'beto.nuevo'))
  })

  it('no guarda un username inválido', async () => {
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Editar usuario' }))
    const dialogo = within(await screen.findByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText('Usuario'), { target: { value: 'b' } })
    fireEvent.submit(dialogo.getByRole('button', { name: 'Guardar' }).closest('form')!)

    expect(await dialogo.findByText(ERROR_USERNAME)).toBeInTheDocument()
    expect(cambiarUsernameUsuario).not.toHaveBeenCalled()
  })

  it('muestra el 409 del backend al editar un username duplicado', async () => {
    vi.mocked(cambiarUsernameUsuario).mockRejectedValue(new ApiError(DUPLICADO, 409))
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Editar usuario' }))
    const dialogo = within(await screen.findByRole('dialog'))
    fireEvent.change(dialogo.getByLabelText('Usuario'), { target: { value: 'ana' } })
    fireEvent.submit(dialogo.getByRole('button', { name: 'Guardar' }).closest('form')!)

    expect(await dialogo.findByText(DUPLICADO)).toBeInTheDocument()
  })
})

describe('GestionUsuarios: comportamiento previo (S6)', () => {
  beforeEach(() => {
    perfilMock.rol = 'admin'
    perfilMock.id = 'yo'
    vi.mocked(listarUsuarios).mockResolvedValue([usuario('Beto', 'comercial')])
    vi.mocked(cambiarActivoUsuario).mockReset().mockResolvedValue(usuario('Beto', 'comercial'))
    vi.mocked(cambiarRolUsuario).mockReset().mockResolvedValue(usuario('Beto', 'compras'))
  })

  it('desactivar sigue llamando a cambiarActivoUsuario', async () => {
    renderPantalla()
    fireEvent.click((await fila('Beto')).getByRole('button', { name: 'Desactivar' }))
    await waitFor(() => expect(cambiarActivoUsuario).toHaveBeenCalledWith('Beto', false))
  })

  it('cambiar el rol sigue llamando a cambiarRolUsuario', async () => {
    renderPantalla()
    fireEvent.change((await fila('Beto')).getByRole('combobox'), { target: { value: 'compras' } })
    await waitFor(() => expect(cambiarRolUsuario).toHaveBeenCalledWith('Beto', 'compras'))
  })
})
