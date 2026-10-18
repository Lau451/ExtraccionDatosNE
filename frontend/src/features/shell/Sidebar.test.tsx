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

describe('Sidebar: matriz de roles', () => {
  it.each<Rol>(['admin', 'gerencia', 'lider_comercial', 'comercial'])('S1/S2: muestra carga y validación a %s', (rol) => {
    rolActual.valor = rol
    render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'Carga de documentos' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Validar extracción' })).toBeTruthy()
  })

  it.each<Rol>(['compras', 'superadmin'])('S1/S2: oculta carga y validación a %s', (rol) => {
    rolActual.valor = rol
    render(<Sidebar />)
    expect(screen.queryByText('Carga de documentos')).toBeNull()
    expect(screen.queryByText('Validar extracción')).toBeNull()
  })

  it('S6: "Importar presupuestos" solo para admin', () => {
    rolActual.valor = 'admin'
    const { unmount } = render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'Importar presupuestos' })).toBeTruthy()
    unmount()
    for (const rol of ['gerencia', 'compras'] as Rol[]) {
      rolActual.valor = rol
      const r = render(<Sidebar />)
      expect(screen.queryByText('Importar presupuestos')).toBeNull()
      r.unmount()
    }
  })

  it('S7: "Usuarios" visible para gerencia', () => {
    rolActual.valor = 'gerencia'
    render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'Usuarios' })).toBeTruthy()
  })

  it('S10: "Usuarios" sigue oculto para comercial y PCP sigue visible para compras', () => {
    rolActual.valor = 'comercial'
    const { unmount } = render(<Sidebar />)
    expect(screen.queryByText('Usuarios')).toBeNull()
    unmount()
    rolActual.valor = 'compras'
    render(<Sidebar />)
    expect(screen.getByRole('link', { name: 'PCP' })).toBeTruthy()
  })
})
