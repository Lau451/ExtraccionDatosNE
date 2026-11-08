import type { Session } from '@supabase/supabase-js'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { iniciarSesion } from '@/lib/api/auth'
import { ApiError, presupuestacionFetch } from '@/lib/api/presupuestacion'
import { supabase } from '@/lib/supabase'
import type { Capacidad } from './capacidades'

// Duplicado a propósito de `Rol` en services/presupuestacion/usuarios/models.py:5 —
// no hay generación de tipos entre ambos proyectos. Si cambia una lista, cambiar la otra.
export type Rol = 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras'

export interface Perfil {
  id: string
  drogueria_id: string | null
  rol: Rol
  nombre: string
  apellido: string | null
  es_sistema: boolean
  activo: boolean
  username: string
  // Cuenta creada o blanqueada por un admin: mientras esté en true, el
  // backend rechaza todo salvo leer el propio perfil y cambiar la contraseña,
  // y los guards mandan a /cambiar-password (spec S3).
  debe_cambiar_password: boolean
}

interface AuthContextValue {
  session: Session | null
  perfil: Perfil | null
  isAuthenticated: boolean
  loading: boolean
  perfilLoading: boolean
  // Capacidades del rol (GET /auth/capacidades, spec S7). Vacía mientras la
  // contraseña sea temporal: el backend responde 403 hasta que se cambie.
  capacidades: Capacidad[]
  // Mensaje cuando GET /auth/capacidades falla por otra cosa que el 403 de la
  // contraseña temporal (500, red caída): sin él, la app quedaba sin permisos
  // y sin avisar. refrescarPerfil() lo vuelve a intentar y lo limpia.
  errorCapacidades: string | null
  puede: (capacidad: Capacidad) => boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  // Devuelve las capacidades recién cargadas: quien navega justo después (el
  // cambio de contraseña) no puede esperar al próximo render para leerlas.
  refrescarPerfil: () => Promise<Capacidad[]>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [capacidades, setCapacidades] = useState<Capacidad[]>([])
  const [errorCapacidades, setErrorCapacidades] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  // Segundo paso asíncrono (perfil + capacidades), distinto de `loading` (que
  // solo cubre la resolución de la sesión de Supabase). Sin este estado
  // separado, el router se monta con perfil=null apenas la sesión resuelve, y
  // requireCapacidad() rebota a "/" porque todavía no llegó el GET
  // /usuarios/{id} — reproducido en sesión de testing manual: recargar /admin/usuarios (deep-link) redirigía
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
  // `session`) y signIn() resolvía apenas el login terminaba, antes
  // de que perfil estuviera listo. LoginForm navega apenas signIn() resuelve
  // (a `?redirect=`, que puede ser una ruta con requireCapacidad) — reproducido
  // en sesión de testing manual: login → redirect directo a /superadmin/empresas
  // aterrizaba en "/" porque el guard corría con perfil todavía null.
  async function cargarPerfil(userId: string): Promise<Capacidad[]> {
    // Las capacidades fallan aparte y nunca cierran la sesión: con la
    // contraseña temporal el backend responde 403 (L5) y la lista queda vacía
    // hasta que refrescarPerfil() la vuelve a pedir después del cambio. Cualquier
    // otro fallo queda en `errorCapacidades` para que la UI lo muestre.
    let fallo: string | null = null
    const capacidadesPromise = presupuestacionFetch<{ rol: string; capacidades: Capacidad[] }>('/auth/capacidades')
      .then((respuesta) => respuesta.capacidades ?? [])
      .catch((error: unknown) => {
        if (!(error instanceof ApiError && error.status === 403)) {
          const detalle = error instanceof Error ? error.message : String(error)
          fallo = `No se pudieron cargar los permisos de tu usuario (${detalle}).`
        }
        return [] as Capacidad[]
      })
    try {
      const [perfilCargado, capacidadesCargadas] = await Promise.all([
        presupuestacionFetch<Perfil>(`/usuarios/${userId}`),
        capacidadesPromise,
      ])
      setPerfil(perfilCargado)
      setCapacidades(capacidadesCargadas)
      setErrorCapacidades(fallo)
      return capacidadesCargadas
    } catch (error) {
      setPerfil(null)
      setCapacidades([])
      setErrorCapacidades(null)
      // 401 (usuario desactivado, ver core/auth.py get_current_user) o 404
      // (fila borrada) con una sesión de Supabase todavía válida — sin este
      // signOut, la UI queda mostrando "Cargando…" para siempre (perfil
      // nunca llega, pero isAuthenticated sigue en true). Reproducido en
      // sesión de testing manual.
      if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
        await supabase.auth.signOut()
      }
      return []
    }
  }

  useEffect(() => {
    // No arrancar hasta saber de verdad si hay sesión — si no, esta rama
    // "sin sesión" corre primero con el `session` inicial (null) y apaga
    // perfilLoading antes de que getSession() haya resuelto nada.
    if (loading) return

    if (!session) {
      setPerfil(null)
      setCapacidades([])
      setErrorCapacidades(null)
      setPerfilLoading(false)
      return
    }

    setPerfilLoading(true)
    // El JWT de Supabase no trae el rol como claim — se resuelve con el mismo
    // GET que ya usa el backend en core/auth.py (SELECT a `usuarios` vía RLS).
    cargarPerfil(session.user.id).finally(() => setPerfilLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a propósito:
    // depender de `session` completo (en vez de session?.user.id) hacía que
    // CUALQUIER evento de onAuthStateChange recargara el perfil y, con eso,
    // tirara abajo toda la app (InnerApp en main.tsx devuelve null mientras
    // perfilLoading). El SDK de Supabase refresca el token solo cada vez que
    // la pestaña recupera el foco, disparando un evento con el mismo usuario
    // — eso se veía como "recargar todo" al volver a la pestaña. Sólo
    // importa si CAMBIÓ el usuario real, no cada renovación de token.
  }, [session?.user.id, loading])

  async function refrescarPerfil(): Promise<Capacidad[]> {
    if (!session) return []
    return cargarPerfil(session.user.id)
  }

  async function signIn(username: string, password: string) {
    // El login va por el backend (spec S1): resuelve el username al email
    // interno de auth del lado del servidor y devuelve la sesión de Supabase,
    // que se instala acá para que supabase-js la refresque como siempre.
    const login = await iniciarSesion(username, password)
    const { error } = await supabase.auth.setSession({
      access_token: login.access_token,
      refresh_token: login.refresh_token,
    })
    if (error) throw error
    // Esperar el perfil ACÁ, no solo dejar que el efecto reactivo lo cargue
    // solo — LoginForm navega apenas esta promesa resuelve.
    await cargarPerfil(login.user.id)
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
        capacidades,
        errorCapacidades,
        puede: (capacidad) => capacidades.includes(capacidad),
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
