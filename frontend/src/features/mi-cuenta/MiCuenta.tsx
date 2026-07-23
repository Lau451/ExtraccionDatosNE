import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useAuth } from '@/features/auth/AuthContext'
import { actualizarPerfilPropio } from '@/lib/api/usuarios'
import { supabase } from '@/lib/supabase'

export function MiCuenta() {
  const { perfil, session, signOut } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await signOut()
    navigate({ to: '/login' })
  }

  if (!perfil) return null

  return (
    <div className="mx-auto max-w-xl space-y-8 p-8">
      <h1 className="text-xl font-semibold text-navy">Mi cuenta</h1>

      <EditarNombreForm nombre={perfil.nombre} apellido={perfil.apellido ?? ''} />
      <CambiarPasswordForm />
      <CambiarEmailForm emailActual={session?.user.email ?? ''} />

      <div className="border-t border-slate-200 pt-6">
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
        >
          Cerrar sesión
        </button>
      </div>
    </div>
  )
}

function EditarNombreForm({ nombre, apellido }: { nombre: string; apellido: string }) {
  const { refrescarPerfil } = useAuth()
  const [values, setValues] = useState({ nombre, apellido })
  const [guardado, setGuardado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setGuardado(false)
    setIsSubmitting(true)
    try {
      await actualizarPerfilPropio(values)
      await refrescarPerfil()
      setGuardado(true)
    } catch {
      setError('No pudimos guardar los cambios.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-sm font-semibold text-slate-700">Datos personales</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label htmlFor="nombre" className="mb-1 block text-sm text-slate-600">
            Nombre
          </label>
          <input
            id="nombre"
            required
            value={values.nombre}
            onChange={(event) => setValues((v) => ({ ...v, nombre: event.target.value }))}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="apellido" className="mb-1 block text-sm text-slate-600">
            Apellido
          </label>
          <input
            id="apellido"
            value={values.apellido}
            onChange={(event) => setValues((v) => ({ ...v, apellido: event.target.value }))}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {guardado && <p className="text-sm text-emerald-600">Guardado.</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {isSubmitting ? 'Guardando…' : 'Guardar'}
        </button>
      </form>
    </section>
  )
}

function CambiarPasswordForm() {
  const [password, setPassword] = useState('')
  const [confirmacion, setConfirmacion] = useState('')
  const [guardado, setGuardado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setGuardado(false)

    if (password !== confirmacion) {
      setError('Las contraseñas no coinciden')
      return
    }

    setIsSubmitting(true)
    try {
      const { error } = await supabase.auth.updateUser({ password })
      if (error) throw error
      setPassword('')
      setConfirmacion('')
      setGuardado(true)
    } catch {
      setError('No pudimos cambiar la contraseña.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="space-y-4 border-t border-slate-200 pt-6">
      <h2 className="text-sm font-semibold text-slate-700">Cambiar contraseña</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label htmlFor="nueva-password" className="mb-1 block text-sm text-slate-600">
            Contraseña nueva
          </label>
          <input
            id="nueva-password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="confirmar-password" className="mb-1 block text-sm text-slate-600">
            Repetir contraseña
          </label>
          <input
            id="confirmar-password"
            type="password"
            required
            autoComplete="new-password"
            value={confirmacion}
            onChange={(event) => setConfirmacion(event.target.value)}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {guardado && <p className="text-sm text-emerald-600">Contraseña actualizada.</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {isSubmitting ? 'Guardando…' : 'Cambiar contraseña'}
        </button>
      </form>
    </section>
  )
}

function CambiarEmailForm({ emailActual }: { emailActual: string }) {
  const [email, setEmail] = useState('')
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setEnviado(false)
    setIsSubmitting(true)
    try {
      const { error } = await supabase.auth.updateUser({ email })
      if (error) throw error
      setEnviado(true)
    } catch {
      setError('No pudimos iniciar el cambio de email.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="space-y-4 border-t border-slate-200 pt-6">
      <h2 className="text-sm font-semibold text-slate-700">Cambiar email</h2>
      <p className="text-xs text-slate-500">
        Email actual: {emailActual || 'sin cargar'}. Supabase va a pedir confirmar el cambio desde
        el email actual y desde el nuevo antes de aplicarlo.
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label htmlFor="nuevo-email" className="mb-1 block text-sm text-slate-600">
            Email nuevo
          </label>
          <input
            id="nuevo-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {enviado && (
          <p className="text-sm text-emerald-600">
            Te enviamos un link de confirmación a tu email actual y al nuevo.
          </p>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {isSubmitting ? 'Enviando…' : 'Cambiar email'}
        </button>
      </form>
    </section>
  )
}
