import { describe, expect, it } from 'vitest'
import type { Rol } from '@/features/auth/AuthContext'
import {
  CATALOGOS_COMERCIALES_WRITE_ROLES,
  TERCEROS_READ_ROLES,
  TERCEROS_WRITE_ROLES,
  puedeRol,
} from './roles'

const TODOS: Rol[] = ['superadmin', 'admin', 'gerencia', 'lider_comercial', 'comercial', 'compras']

describe('S4: escritura de terceros', () => {
  it('solo admin, gerencia y lider_comercial escriben', () => {
    expect(TODOS.filter((rol) => puedeRol(rol, TERCEROS_WRITE_ROLES))).toEqual(['admin', 'gerencia', 'lider_comercial'])
  })

  it('la lectura sigue abierta a los 6 roles', () => {
    expect(TODOS.every((rol) => puedeRol(rol, TERCEROS_READ_ROLES))).toBe(true)
  })
})

describe('S5: catálogos de apoyo', () => {
  it('admin, gerencia y lider_comercial gestionan catálogos', () => {
    expect(TODOS.filter((rol) => puedeRol(rol, CATALOGOS_COMERCIALES_WRITE_ROLES))).toEqual([
      'admin',
      'gerencia',
      'lider_comercial',
    ])
  })
})
