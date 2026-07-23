import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { supabase } from '@/lib/supabase'

export function SetPasswordForm({
  title,
  submitLabel = 'Guardar contraseña',
}: {
  title: string
  submitLabel?: string
}) {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    if (password !== confirmacion) {
      setError('Las contraseñas no coinciden')
      return
    }

    setIsSubmitting(true)
    try {
      const { error } = await supabase.auth.updateUser({ password })
      if (error) throw error
      await supabase.auth.signOut()
      navigate({ to: '/login' })
    } catch {
      setError('No pudimos guardar la contraseña. Probá de nuevo.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
      <p className="text-sm text-slate-600">{title}</p>

      <div>
        <label htmlFor="password" className="mb-1 block text-sm text-slate-600">
          Contraseña nueva
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label htmlFor="confirmacion" className="mb-1 block text-sm text-slate-600">
          Repetir contraseña
        </label>
        <input
          id="confirmacion"
          type="password"
          required
          autoComplete="new-password"
          value={confirmacion}
          onChange={(event) => setConfirmacion(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-navy py-2.5 text-sm font-semibold text-white disabled:opacity-40"
      >
        {isSubmitting ? 'Guardando…' : submitLabel}
      </button>
    </form>
  )
}
