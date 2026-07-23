import { createFileRoute, Outlet, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { requireAuth } from '@/features/auth/routeGuards'
import { Sidebar } from '@/features/shell/Sidebar'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: requireAuth,
  component: AuthenticatedLayout,
})

function AuthenticatedLayout() {
  const { isAuthenticated } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    // requireAuth (beforeLoad) solo corre al entrar a la ruta — si la sesión
    // se invalida DESPUÉS (logout en otra pestaña, usuario desactivado/
    // eliminado — ver AuthContext.tsx signOut en el catch del perfil), esta
    // pantalla se quedaba montada sin redirigir. Chequeo reactivo acá.
    if (!isAuthenticated) {
      navigate({ to: '/login' })
    }
  }, [isAuthenticated, navigate])

  return (
    <div className="flex min-h-svh bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
