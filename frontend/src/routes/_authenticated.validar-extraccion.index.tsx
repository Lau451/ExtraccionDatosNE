import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ValidarExtraccionListado } from '@/features/validar-extraccion/ValidarExtraccionListado'
import { VALIDAR_EXTRACCION_ROLES } from '@/features/validar-extraccion/roles'

export const Route = createFileRoute('/_authenticated/validar-extraccion/')({
  beforeLoad: requireRole(...VALIDAR_EXTRACCION_ROLES),
  component: ValidarExtraccionListado,
})
