import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { GestionPcp } from '@/features/pcp/GestionPcp'

export const Route = createFileRoute('/_authenticated/pcp/')({
  beforeLoad: requireCapacidad('pcp.leer'),
  component: GestionPcp,
})
