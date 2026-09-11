import { createFileRoute, Outlet } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { PCP_READ_ROLES } from '@/features/pcp/roles'

export const Route = createFileRoute('/_authenticated/pcp')({
  beforeLoad: requireRole(...PCP_READ_ROLES),
  component: Outlet,
})
