import { useState } from 'react'
import { ApiError } from '@/lib/api/presupuestacion'
import { useAuth } from './AuthContext'

export function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const { signIn } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await signIn(username.trim(), password)
      onSuccess()
    } catch (error) {
      console.error('Error al iniciar sesión', error)
      // El backend devuelve el mismo 401 para usuario inexistente y contraseña
      // incorrecta, así no se pueden sondear usernames (spec S1). El 429 trae
      // su propio mensaje (spec S8) para no confundirlo con credenciales mal.
      if (error instanceof ApiError && error.status === 429) {
        setError(error.message)
      } else {
        setError(
          error instanceof ApiError && error.status !== 401
            ? 'No pudimos iniciar sesión. Probá de nuevo.'
            : 'Usuario o contraseña incorrectos',
        )
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
      <div>
        <label htmlFor="username" className="mb-1 block text-sm text-slate-600">
          Usuario
        </label>
        <input
          id="username"
          type="text"
          required
          autoCapitalize="none"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label htmlFor="password" className="mb-1 block text-sm text-slate-600">
          Contraseña
        </label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-navy py-2.5 text-sm font-semibold text-white disabled:opacity-40"
      >
        {isSubmitting ? 'Ingresando…' : 'Ingresar'}
      </button>

      <p className="text-center text-sm text-slate-500">
        ¿Olvidaste tu contraseña? Contactá al administrador para que te la blanquee.
      </p>
    </form>
  )
}
