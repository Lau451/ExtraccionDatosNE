import type { Session } from '@supabase/supabase-js'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { presupuestacionFetch } from '@/lib/api/presupuestacion'
import { supabase } from '@/lib/supabase'

export type Rol = 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras'

export interface Perfil {
  id: string
  drogueria_id: string | null
  rol: Rol
  nombre: string
  es_sistema: boolean
  activo: boolean
}

interface AuthContextValue {
  session: Session | null
  perfil: Perfil | null
  isAuthenticated: boolean
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [loading, setLoading] = useState(true)

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

  useEffect(() => {
    if (!session) {
      setPerfil(null)
      return
    }
    // El JWT de Supabase no trae el rol como claim — se resuelve con el mismo
    // GET que ya usa el backend en core/auth.py (SELECT a `usuarios` vía RLS).
    presupuestacionFetch<Perfil>(`/usuarios/${session.user.id}`)
      .then(setPerfil)
      .catch(() => setPerfil(null))
  }, [session])

  async function signIn(email: string, password: string) {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{ session, perfil, isAuthenticated: session !== null, loading, signIn, signOut }}
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
