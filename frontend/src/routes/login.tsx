import { createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import { LoginForm } from '@/features/auth/LoginForm'
import { useAuth } from '@/features/auth/AuthContext'

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
  component: LoginPage,
})

// Hard navigation (no router.navigate()) a propósito: requireRole() en
// routeGuards.ts decide en base a auth.perfil del context del router, que
// solo se actualiza cuando React vuelve a renderizar — setPerfil() (dentro de
// signIn(), AuthContext.tsx) es asíncrono, así que navigate() puede correr
// ANTES de ese re-render y el guard ve perfil=null. Reproducido en sesión de
// testing manual: login → redirect a /superadmin/empresas aterrizaba en "/"
// pese a que el usuario era superadmin. Un reload completo evita la carrera
// por completo: InnerApp (main.tsx) ya espera loading/perfilLoading antes de
// montar el router, así que al recargar el context llega siempre resuelto.
function irA(destino: string) {
  window.location.href = destino
}

function LoginPage() {
  const { isAuthenticated } = useAuth()
  const { redirect } = Route.useSearch()

  useEffect(() => {
    if (isAuthenticated) {
      irA(redirect ?? '/')
    }
  }, [isAuthenticated, redirect])

  return (
    <div className="flex min-h-svh items-center justify-center bg-slate-50">
      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-lg font-semibold text-navy">Droguería Nueva Era</h1>
        <LoginForm onSuccess={() => irA(redirect ?? '/')} />
      </div>
    </div>
  )
}
