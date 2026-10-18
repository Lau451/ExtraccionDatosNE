import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { Compromisos } from '@/features/compromisos/Compromisos'
import { COMPROMISOS_READ_ROLES } from '@/features/compromisos/roles'

export const Route = createFileRoute('/_authenticated/compromisos')({
  beforeLoad: requireRole(...COMPROMISOS_READ_ROLES),
  component: Compromisos,
})
