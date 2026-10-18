import { createFileRoute } from '@tanstack/react-router'
import { GestionUsuarios } from '@/features/gestion-usuarios/GestionUsuarios'
import { requireRole } from '@/features/auth/routeGuards'
import { USUARIOS_ROLES } from '@/features/gestion-usuarios/roles'

export const Route = createFileRoute('/_authenticated/admin/usuarios')({
  beforeLoad: requireRole(...USUARIOS_ROLES),
  component: GestionUsuarios,
})
