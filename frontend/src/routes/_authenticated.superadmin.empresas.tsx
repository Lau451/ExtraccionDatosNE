import { createFileRoute } from '@tanstack/react-router'
import { GestionEmpresas } from '@/features/gestion-empresas/GestionEmpresas'
import { requireCapacidad } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/superadmin/empresas')({
  beforeLoad: requireCapacidad('droguerias.gestionar'),
  component: GestionEmpresas,
})
