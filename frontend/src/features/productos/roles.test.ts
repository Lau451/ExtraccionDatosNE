import { describe, expect, it } from 'vitest'
import { COSTOS_READ_ROLES, puedeRol } from './roles'

describe('S3: ver costos', () => {
  it('lider_comercial puede ver costos', () => {
    expect(puedeRol('lider_comercial', COSTOS_READ_ROLES)).toBe(true)
  })

  it('comercial sigue sin ver costos; superadmin, admin, gerencia y compras siguen viéndolos', () => {
    expect(puedeRol('comercial', COSTOS_READ_ROLES)).toBe(false)
    expect(['superadmin', 'admin', 'gerencia', 'compras'].every((rol) => puedeRol(rol as never, COSTOS_READ_ROLES))).toBe(true)
  })
})
