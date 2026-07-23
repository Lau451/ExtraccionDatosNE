import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

/** Tanto el link de invitación como el de recuperación de contraseña dejan al
 * navegador con una sesión temporal apenas supabase-js procesa el fragmento
 * de la URL (detectSessionInUrl, default true). Este hook espera esa sesión
 * antes de mostrar el formulario de "definir contraseña" — evita mostrarlo
 * antes de tiempo o dejarlo mudo si el link es inválido/expiró. */
export function useSessionFromLink() {
  const [checking, setChecking] = useState(true)
  const [hasSession, setHasSession] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setHasSession(data.session !== null)
      setChecking(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setHasSession(session !== null)
      setChecking(false)
    })

    return () => subscription.unsubscribe()
  }, [])

  return { checking, hasSession }
}
