import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error('Faltan VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY en el .env de frontend/')
}

/** Uso exclusivo: login/logout y lectura de la sesión (JWT) — Paso 0 acordado.
 * Ningún dato de negocio se consulta con este cliente; todo pasa por los
 * backends (`extraccionFetch`/`presupuestacionFetch`), que ya aplican RLS
 * con el JWT del usuario. */
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
