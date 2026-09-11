import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { GestionCatalogoProveedores } from '@/features/pcp/GestionCatalogoProveedores'
import { PCP_READ_ROLES } from '@/features/pcp/roles'

export const Route = createFileRoute('/_authenticated/pcp/catalogo')({
  beforeLoad: requireRole(...PCP_READ_ROLES),
  component: GestionCatalogoProveedores,
})
