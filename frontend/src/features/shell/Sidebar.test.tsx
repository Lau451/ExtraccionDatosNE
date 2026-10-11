import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'

const { rolActual } = vi.hoisted(() => ({ rolActual: { valor: 'admin' as string } }))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to }: { children?: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => vi.fn(),
}))
vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: { rol: rolActual.valor, nombre: 'Test' }, signOut: vi.fn() }),
}))

import { Sidebar } from './Sidebar'

describe('Sidebar: Compromisos de entrega', () => {
  beforeEach(() => {
    rolActual.valor = 'admin'
  })

  it.each<Rol>(['admin', 'gerencia', 'lider_comercial', 'comercial', 'compras'])('visible para %s', (rol) => {
    rolActual.valor = rol
    render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'Compromisos de entrega' }).getAttribute('href')).toBe('/compromisos')
  })

  it('oculto para superadmin (no tiene droguería)', () => {
    rolActual.valor = 'superadmin'
    render(<Sidebar />)
    expect(screen.queryByText('Compromisos de entrega')).toBeNull()
  })

  it('oculto para el rol sistema', () => {
    rolActual.valor = 'sistema'
    render(<Sidebar />)
    expect(screen.queryByText('Compromisos de entrega')).toBeNull()
  })
})
