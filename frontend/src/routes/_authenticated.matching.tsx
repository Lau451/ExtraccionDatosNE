import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ProcesosMatchingListado } from '@/features/proceso-matching/ProcesosMatchingListado'

export const Route = createFileRoute('/_authenticated/matching')({
  beforeLoad: requireCapacidad('matching.usar'),
  component: ProcesosMatchingListado,
})
