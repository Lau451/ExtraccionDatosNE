import { createFileRoute } from '@tanstack/react-router'
import { GestionEmpresas } from '@/features/gestion-empresas/GestionEmpresas'
import { requireRole } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/superadmin/empresas')({
  beforeLoad: requireRole('superadmin'),
  component: GestionEmpresas,
})
