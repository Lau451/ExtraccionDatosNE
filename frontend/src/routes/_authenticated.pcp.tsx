import { createFileRoute, Outlet } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/pcp')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: Outlet,
})
