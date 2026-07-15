import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect } from 'react'
import { LoginForm } from '@/features/auth/LoginForm'
import { useAuth } from '@/features/auth/AuthContext'

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
  component: LoginPage,
})

function LoginPage() {
  const { isAuthenticated } = useAuth()
  const { redirect } = Route.useSearch()
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) {
      navigate({ to: redirect ?? '/' })
    }
  }, [isAuthenticated, redirect, navigate])

  return (
    <div className="flex min-h-svh items-center justify-center bg-slate-50">
      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-lg font-semibold text-navy">Droguería Nueva Era</h1>
        <LoginForm onSuccess={() => navigate({ to: redirect ?? '/' })} />
      </div>
    </div>
  )
}
