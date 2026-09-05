import { createFileRoute } from '@tanstack/react-router'
import { GestionProductos } from '@/features/productos/GestionProductos'
import { requireRole } from '@/features/auth/routeGuards'
import { PRODUCTOS_READ_ROLES } from '@/features/productos/roles'

export const Route = createFileRoute('/_authenticated/productos')({
  beforeLoad: requireRole(...PRODUCTOS_READ_ROLES),
  component: GestionProductos,
})
