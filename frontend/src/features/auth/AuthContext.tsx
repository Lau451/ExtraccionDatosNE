import type { Session } from '@supabase/supabase-js'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { ApiError, presupuestacionFetch } from '@/lib/api/presupuestacion'
import { supabase } from '@/lib/supabase'

export type Rol = 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras'

export interface Perfil {
  id: string
  drogueria_id: string | null
  rol: Rol
  nombre: string
  apellido: string | null
  es_sistema: boolean
  activo: boolean
}

interface AuthContextValue {
  session: Session | null
  perfil: Perfil | null
  isAuthenticated: boolean
  loading: boolean
  perfilLoading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  refrescarPerfil: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [loading, setLoading] = useState(true)
  // Segundo paso asíncrono, distinto de `loading` (que solo cubre la
  // resolución de la sesión de Supabase). Sin este estado separado, el router
  // se monta con perfil=null apenas la sesión resuelve, y requireRole()
  // rebota a "/" porque todavía no llegó el GET /usuarios/{id} — reproducido
  // en sesión de testing manual: recargar /admin/usuarios (deep-link) redirigía
  // a "/" pese a estar autenticado con el rol correcto.
  const [perfilLoading, setPerfilLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession)
    })

    return () => subscription.unsubscribe()
  }, [])

  // Extraído para poder esperarlo explícitamente desde signIn() — sin esto,
  // el fetch de perfil solo se disparaba de forma reactiva (efecto sobre
  // `session`) y signIn() resolvía apenas signInWithPassword terminaba, antes
  // de que perfil estuviera listo. LoginForm navega apenas signIn() resuelve
  // (a `?redirect=`, que puede ser una ruta con requireRole) — reproducido en
  // sesión de testing manual: login → redirect directo a /superadmin/empresas
  // aterrizaba en "/" porque requireRole corría con perfil todavía null.
  async function cargarPerfil(userId: string): Promise<void> {
    try {
      const perfilCargado = await presupuestacionFetch<Perfil>(`/usuarios/${userId}`)
      setPerfil(perfilCargado)
    } catch (error) {
      setPerfil(null)
      // 401 (usuario desactivado, ver core/auth.py get_current_user) o 404
      // (fila borrada) con una sesión de Supabase todavía válida — sin este
      // signOut, la UI queda mostrando "Cargando…" para siempre (perfil
      // nunca llega, pero isAuthenticated sigue en true). Reproducido en
      // sesión de testing manual.
      if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
        await supabase.auth.signOut()
      }
    }
  }

  useEffect(() => {
    // No arrancar hasta saber de verdad si hay sesión — si no, esta rama
    // "sin sesión" corre primero con el `session` inicial (null) y apaga
    // perfilLoading antes de que getSession() haya resuelto nada.
    if (loading) return

    if (!session) {
      setPerfil(null)
      setPerfilLoading(false)
      return
    }

    setPerfilLoading(true)
    // El JWT de Supabase no trae el rol como claim — se resuelve con el mismo
    // GET que ya usa el backend en core/auth.py (SELECT a `usuarios` vía RLS).
    cargarPerfil(session.user.id).finally(() => setPerfilLoading(false))
  }, [session, loading])

  async function refrescarPerfil() {
    if (!session) return
    await cargarPerfil(session.user.id)
  }

  async function signIn(email: string, password: string) {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    // Esperar el perfil ACÁ, no solo dejar que el efecto reactivo lo cargue
    // solo — LoginForm navega apenas esta promesa resuelve.
    if (data.user) {
      await cargarPerfil(data.user.id)
    }
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{
        session,
        perfil,
        isAuthenticated: session !== null,
        loading,
        perfilLoading,
        signIn,
        signOut,
        refrescarPerfil,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return context
}
