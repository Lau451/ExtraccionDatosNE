import { createFileRoute } from '@tanstack/react-router'
import { GestionTerceros } from '@/features/terceros/GestionTerceros'
import { requireRole } from '@/features/auth/routeGuards'
import { TERCEROS_READ_ROLES } from '@/features/terceros/roles'

export const Route = createFileRoute('/_authenticated/terceros')({
  beforeLoad: requireRole(...TERCEROS_READ_ROLES),
  component: GestionTerceros,
})
