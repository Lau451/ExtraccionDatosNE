import { createFileRoute } from '@tanstack/react-router'
import { requireRole } from '@/features/auth/routeGuards'
import { ProcesosMatchingListado } from '@/features/proceso-matching/ProcesosMatchingListado'
import { MATCHING_ROLES } from '@/features/proceso-matching/roles'

export const Route = createFileRoute('/_authenticated/matching')({
  beforeLoad: requireRole(...MATCHING_ROLES),
  component: ProcesosMatchingListado,
})
