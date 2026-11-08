import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ValidarExtraccionListado } from '@/features/validar-extraccion/ValidarExtraccionListado'

export const Route = createFileRoute('/_authenticated/validar-extraccion/')({
  beforeLoad: requireCapacidad('extraccion.validar'),
  component: ValidarExtraccionListado,
})
