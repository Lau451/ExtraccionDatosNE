import { createFileRoute, Outlet } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { PRODUCTOS_READ_ROLES } from '@/features/productos/roles'

export const Route = createFileRoute('/_authenticated/productos')({
  beforeLoad: requireRole(...PRODUCTOS_READ_ROLES),
  component: Outlet,
})
