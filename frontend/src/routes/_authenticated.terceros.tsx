import { createFileRoute, Outlet } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { TERCEROS_READ_ROLES } from '@/features/terceros/roles'

export const Route = createFileRoute('/_authenticated/terceros')({
  beforeLoad: requireRole(...TERCEROS_READ_ROLES),
  component: Outlet,
})
