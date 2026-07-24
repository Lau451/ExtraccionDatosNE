import { createFileRoute, Link } from '@tanstack/react-router'
import { useState } from 'react'
import { SetPasswordForm } from '@/features/auth/SetPasswordForm'
import { useSessionFromLink } from '@/features/auth/useSessionFromLink'
import { supabase } from '@/lib/supabase'

export const Route = createFileRoute('/reset-password')({
  component: ResetPasswordPage,
})

function ResetPasswordPage() {
  const { checking, hasSession } = useSessionFromLink()

  return (
    <div className="flex min-h-svh items-center justify-center bg-slate-50">
      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-lg font-semibold text-navy">Droguería Nueva Era</h1>
        {checking ? (
          <p className="text-sm text-slate-500">Verificando…</p>
        ) : hasSession ? (
          <SetPasswordForm title="Elegí tu nueva contraseña" />
        ) : (
          <SolicitarResetForm />
        )}
      </div>
    </div>
  )
}

function SolicitarResetForm() {
  const [email, setEmail] = useState('')
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      })
      if (error) throw error
      setEnviado(true)
    } catch (error) {
      console.error('Error al solicitar el reset de contraseña', error)
      setError('No pudimos enviar el mail. Probá de nuevo.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (enviado) {
    return (
      <p className="w-full max-w-sm text-sm text-slate-600">
        Si el email existe en el sistema, te enviamos un link para restablecer tu contraseña.
      </p>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
      <p className="text-sm text-slate-600">
        Ingresá tu email y te enviamos un link para restablecer tu contraseña.
      </p>

      <div>
        <label htmlFor="email" className="mb-1 block text-sm text-slate-600">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-navy py-2.5 text-sm font-semibold text-white disabled:opacity-40"
      >
        {isSubmitting ? 'Enviando…' : 'Enviar link de recuperación'}
      </button>

      <Link to="/login" className="block text-center text-sm text-accent">
        Volver al login
      </Link>
    </form>
  )
}
