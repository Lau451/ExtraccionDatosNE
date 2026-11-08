import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { Compromisos } from '@/features/compromisos/Compromisos'

export const Route = createFileRoute('/_authenticated/compromisos')({
  beforeLoad: requireCapacidad('compromisos.ver_pantalla'),
  component: Compromisos,
})
