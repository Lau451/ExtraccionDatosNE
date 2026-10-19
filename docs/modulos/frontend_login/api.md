# API pública — Login

Firmas verificadas contra el código de la rama `feat/login-usuario-alta-admin`.

## `lib/supabase.ts`

```typescript
export const supabase: SupabaseClient
// supabase.ts:14 — createClient(SUPABASE_URL, SUPABASE_ANON_KEY), único cliente supabase-js.
// Uso: sesión (setSession/getSession/onAuthStateChange/refresh) y logout. Ya no hace sign-in.
```

## `lib/api/auth.ts` — **[NUEVO]**

```typescript
export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  expires_at: number
  token_type: string
  user: { id: string }
}
// auth.ts:6-13 — campos de sesión que devuelve POST /auth/login.

export interface CambiarPasswordPayload {
  password_actual: string
  password_nueva: string
}
// auth.ts:15-18

export async function iniciarSesion(username: string, password: string): Promise<LoginResponse>
// auth.ts:22-37 — fetch directo a `${PRESUPUESTACION_BASE_URL}/auth/login` (no usa
// presupuestacionFetch, para no mandar el Authorization de una sesión vieja, :20-21). Si la
// respuesta no es ok, lanza ApiError(detail ?? `Error ${status} al iniciar sesión`, status).

export function cambiarPasswordPropia(payload: CambiarPasswordPayload): Promise<void>
// auth.ts:39-45 — presupuestacionFetch POST /auth/cambiar-password (con Authorization).
```

## `features/auth/AuthContext.tsx`

```typescript
export type Rol = 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras'
// AuthContext.tsx:9

export interface Perfil {
  id: string
  drogueria_id: string | null
  rol: Rol
  nombre: string
  apellido: string | null
  es_sistema: boolean
  activo: boolean
  username: string                // NUEVO
  debe_cambiar_password: boolean  // NUEVO — mientras sea true, los guards mandan a /cambiar-password
}
// AuthContext.tsx:11-24 — forma de GET /usuarios/{id} (UsuarioOut, ../usuarios/api.md).

interface AuthContextValue {
  session: Session | null
  perfil: Perfil | null
  isAuthenticated: boolean
  loading: boolean
  perfilLoading: boolean
  signIn: (username: string, password: string) => Promise<void>   // antes (email, password)
  signOut: () => Promise<void>
  refrescarPerfil: () => Promise<void>
}
// AuthContext.tsx:26-35 (no exportado)

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element
// AuthContext.tsx:39-156. Efectos:
//   1) getSession() + onAuthStateChange() al montar (:51-64).
//   2) resolución de `perfil` vía cargarPerfil (GET /usuarios/{id}, :73-88) después de (1)
//      (:90-114). Si falla con ApiError 401/404 → supabase.auth.signOut() (:84-86).
// signIn (:121-134): iniciarSesion(username, password) → supabase.auth.setSession({
//   access_token, refresh_token }) (si error, lo relanza) → await cargarPerfil(login.user.id).
// refrescarPerfil (:116-119): vuelve a pedir el perfil (Mi cuenta, CambiarPasswordForm).

export function useAuth(): AuthContextValue
// AuthContext.tsx:158-162
```

## `features/auth/LoginForm.tsx`

```typescript
export function LoginForm({ onSuccess }: { onSuccess: () => void }): JSX.Element
// LoginForm.tsx:5-86. Campos "Usuario" (type="text", autoCapitalize="none",
// autoComplete="username", :40-54) y "Contraseña". signIn(username.trim(), password) (:17).
// Error: 429 → el detail del backend tal cual ("Demasiados intentos. Probá de nuevo en unos
// minutos.", :24-25, RN-LOGIN-013); 401 o error que no es ApiError → "Usuario o contraseña
// incorrectos"; otro ApiError → "No pudimos iniciar sesión. Probá de nuevo." (:26-32). Texto
// fijo "¿Olvidaste tu contraseña? Contactá al administrador para que te la blanquee." (:81-83).
// Ya no enlaza a /reset-password.
```

## `features/auth/routeGuards.ts`

```typescript
interface GuardArgs {
  context: { auth: { isAuthenticated: boolean; perfil: { rol: Rol; debe_cambiar_password?: boolean } | null } }
  location: { href: string }
}
// routeGuards.ts:5-8 (no exportado)

export function requireSession({ context, location }: GuardArgs): void
// routeGuards.ts:12-16 — NUEVO. Solo exige sesión; redirect a /login?redirect=<href>.
// Usado por /cambiar-password (con requireAuth se redirigiría a sí misma).

export function requireAuth(args: GuardArgs): void
// routeGuards.ts:20-25 — requireSession + throw redirect({ to: '/cambiar-password' }) si
// perfil.debe_cambiar_password. Usado en beforeLoad de _authenticated.tsx:8 y por requireRole.

export function homeForRol(rol: Rol | undefined): string
// routeGuards.ts:31-36 — '/' (CARGA_DOCUMENTOS_ROLES), '/productos' (compras),
// '/superadmin/empresas' (superadmin), '/mi-cuenta' sin perfil.

export function requireRole(...roles: Rol[]): (args: GuardArgs) => void
// routeGuards.ts:38-46 — requireAuth + rol en la whitelist; si no, redirect a homeForRol(rol).
```

## `features/auth/CambiarPasswordForm.tsx` — **[NUEVO]**

```typescript
export function CambiarPasswordForm({ onSuccess }: { onSuccess: () => void }): JSX.Element
// CambiarPasswordForm.tsx:11-112. Campos actual / nueva / repetir. Valida en JS (:23-36):
// nueva < 8 → "La contraseña nueva debe tener al menos 8 caracteres"; nueva === actual →
// "La contraseña nueva tiene que ser distinta de la actual"; nueva !== repetir → "Las
// contraseñas no coinciden". Luego cambiarPasswordPropia (:40) → refrescarPerfil() (:43) →
// onSuccess(). Error: muestra ApiError.message (el detail del backend) o un genérico (:47).
```

## `features/auth/CambiarPasswordPage.tsx` — **[NUEVO]**

```typescript
export function CambiarPasswordPage({ irA }: { irA: (destino: string) => void }): JSX.Element
// CambiarPasswordPage.tsx:12-52. forzado = perfil?.debe_cambiar_password (:14). Si forzado,
// muestra "Tu contraseña es temporal. Tenés que cambiarla antes de continuar." (:25-29) y no
// muestra "Cancelar"; si no, "Cancelar" → irA('/mi-cuenta') (:34-41). "Cerrar sesión" siempre
// (:45-47). Éxito → irA(homeForRol(perfil?.rol)) (:31).
```

## `routes/login.tsx`

```typescript
export const Route: FileRoute<'/login'>
// login.tsx:6-11 — validateSearch ({ redirect?: string }); component: LoginPage.
// irA (:22-24) = window.location.href (D-LOGIN-007).
```

## `routes/cambiar-password.tsx` — **[NUEVO]**

```typescript
export const Route: FileRoute<'/cambiar-password'>
// cambiar-password.tsx:7-10 — beforeLoad: requireSession; component: CambiarPasswordPage con
// irA = window.location.href (:13-15, mismo motivo que login.tsx).
```

## `routes/_authenticated.tsx`

```typescript
export const Route: FileRoute<'/_authenticated'>
// _authenticated.tsx:7-10 — beforeLoad: requireAuth (:8). AuthenticatedLayout (:12-39): useEffect
// reactivo (:17-29) → navigate('/login') si isAuthenticated pasa a false, o
// navigate('/cambiar-password') si perfil.debe_cambiar_password pasa a true ya montado.
```

## `routes/__root.tsx`

```typescript
interface RouterContext { auth: ReturnType<typeof useAuth> }
export const Route: RootRoute<RouterContext>
```

## `main.tsx` (fragmento `InnerApp`)

```typescript
function InnerApp(): JSX.Element | null
// main.tsx:22-29 — if (auth.loading || auth.perfilLoading) return null (:27);
// <RouterProvider router={router} context={{ auth }} /> (:28).
```

## Eliminados

`features/auth/SetPasswordForm.tsx`, `features/auth/useSessionFromLink.ts`,
`routes/reset-password.tsx` y `routes/accept-invite.tsx` (commit `0535d4d`).
