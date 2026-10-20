import { useState } from 'react'
import { cambiarPasswordPropia } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/presupuestacion'
import { useAuth } from './AuthContext'

const LARGO_MINIMO = 8

/** Cambio de contraseña propio (spec S3): sirve tanto para el cambio forzado
 * del primer ingreso / después de un blanqueo como para el voluntario desde
 * Mi cuenta. Las reglas se validan acá y el backend las vuelve a validar. */
export function CambiarPasswordForm({ onSuccess }: { onSuccess: () => void }) {
  const { refrescarPerfil } = useAuth()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    if (nueva.length < LARGO_MINIMO) {
      setError(`La contraseña nueva debe tener al menos ${LARGO_MINIMO} caracteres`)
      return
    }

    if (nueva === actual) {
      setError('La contraseña nueva tiene que ser distinta de la actual')
      return
    }

    if (nueva !== confirmacion) {
      setError('Las contraseñas no coinciden')
      return
    }

    setIsSubmitting(true)
    try {
      await cambiarPasswordPropia({ password_actual: actual, password_nueva: nueva })
      // Recargar el perfil para que `debe_cambiar_password` quede en false
      // antes de salir de esta pantalla.
      await refrescarPerfil()
      onSuccess()
    } catch (error) {
      console.error('Error al cambiar la contraseña', error)
      setError(error instanceof ApiError ? error.message : 'No pudimos cambiar la contraseña. Probá de nuevo.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
      <div>
        <label htmlFor="password-actual" className="mb-1 block text-sm text-slate-600">
          Contraseña actual
        </label>
        <input
          id="password-actual"
          type="password"
          required
          autoComplete="current-password"
          value={actual}
          onChange={(event) => setActual(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label htmlFor="password-nueva" className="mb-1 block text-sm text-slate-600">
          Contraseña nueva
        </label>
        <input
          id="password-nueva"
          type="password"
          required
          autoComplete="new-password"
          value={nueva}
          onChange={(event) => setNueva(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <p className="mt-1 text-xs text-slate-500">Mínimo {LARGO_MINIMO} caracteres.</p>
      </div>

      <div>
        <label htmlFor="password-confirmacion" className="mb-1 block text-sm text-slate-600">
          Repetir contraseña nueva
        </label>
        <input
          id="password-confirmacion"
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
        {isSubmitting ? 'Guardando…' : 'Cambiar contraseña'}
      </button>
    </form>
  )
}
