import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
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
  invitarUsuario: vi.fn(),
}))

import { listarUsuarios, type Usuario } from '@/lib/api/usuarios'

function usuario(id: string, rol: string): Usuario {
  return { id, drogueria_id: 'drog-1', rol, nombre: id, apellido: null, es_sistema: false, activo: true }
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

  it('gerencia gestiona roles inferiores y no puede asignar admin (fila e invitación)', async () => {
    perfilMock.rol = 'gerencia'
    renderPantalla()
    const filaComercial = await fila('Beto')
    expect(opcionesDe(filaComercial.getByRole('combobox'))).toEqual(['gerencia', 'lider_comercial', 'comercial', 'compras'])
    expect(filaComercial.getByRole('button', { name: 'Desactivar' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '+ Invitar usuario' }))
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
