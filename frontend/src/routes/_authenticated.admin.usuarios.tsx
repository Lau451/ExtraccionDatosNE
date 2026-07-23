import { createFileRoute } from '@tanstack/react-router'
import { GestionUsuarios } from '@/features/gestion-usuarios/GestionUsuarios'
import { requireRole } from '@/features/auth/routeGuards'

export const Route = createFileRoute('/_authenticated/admin/usuarios')({
  beforeLoad: requireRole('admin', 'superadmin'),
  component: GestionUsuarios,
})
