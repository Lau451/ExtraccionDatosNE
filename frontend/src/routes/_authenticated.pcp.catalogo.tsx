import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { GestionCatalogoProveedores } from '@/features/pcp/GestionCatalogoProveedores'

export const Route = createFileRoute('/_authenticated/pcp/catalogo')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: GestionCatalogoProveedores,
})
