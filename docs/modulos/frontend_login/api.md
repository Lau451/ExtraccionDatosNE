# API pública — Login

Firmas verificadas contra el código real en esta sesión.

## `lib/supabase.ts`

```typescript
export const supabase: SupabaseClient
// supabase.ts:14
// createClient(SUPABASE_URL, SUPABASE_ANON_KEY) — único cliente supabase-js del frontend.
// Uso exclusivo: login/logout/lectura de sesión (comentario explícito, supabase.ts:10-13).
```

## `features/auth/AuthContext.tsx`

```typescript
export type Rol =
  | 'superadmin' | 'admin' | 'gerencia' | 'lider_comercial' | 'comercial' | 'compras'
// AuthContext.tsx:6

export interface Perfil {
  id: string
  drogueria_id: string | null
  rol: Rol
  nombre: string
  apellido: string | null
  es_sistema: boolean
  activo: boolean
}
// AuthContext.tsx:8-16
// Forma esperada de la respuesta de GET /usuarios/{id} — ver ../usuarios/api.md (UsuarioOut).
// `apellido` es campo nuevo (antes solo `nombre`); nullable porque el backend lo modela así.

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
// AuthContext.tsx:18-27 (no exportado — tipo interno del contexto)
// `perfilLoading` y `refrescarPerfil` son nuevos frente a la versión anterior de esta doc.

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element
// AuthContext.tsx:31-120
// Provee AuthContextValue. Efectos:
//   1) getSession() + onAuthStateChange() al montar (:43-56) → resuelve `session`/`loading`.
//   2) resolución de `perfil` vía GET /usuarios/{id}, secuenciado DESPUÉS de (1) — no arranca
//      mientras `loading` sea true (:58-87, guard en :62). Si el fetch falla con status 401 o 404
//      (ApiError, ver ../usuarios/... y core/auth.py `activo`/borrado), hace
//      `supabase.auth.signOut()` automáticamente (:82-84).
// `refrescarPerfil()` (:89-93) vuelve a pedir GET /usuarios/{id} y actualiza `perfil` sin pasar por
// el ciclo de `session` — usado por Mi cuenta tras editar nombre/apellido.

export function useAuth(): AuthContextValue
// AuthContext.tsx:122-126
// Lanza Error('useAuth debe usarse dentro de <AuthProvider>') si se llama fuera del provider (:124).
```

## `features/auth/LoginForm.tsx`

```typescript
export function LoginForm({ onSuccess }: { onSuccess: () => void }): JSX.Element
// LoginForm.tsx:5-73
// Formulario controlado (email, password, error, isSubmitting como estado local).
// No expone props para mensajes de error personalizados ni para prellenar campos.
// Incluye un <Link to="/reset-password"> ("¿Olvidaste tu contraseña?", LoginForm.tsx:68-70).
```

## `features/auth/routeGuards.ts`

```typescript
interface GuardArgs {
  context: { auth: { isAuthenticated: boolean; perfil: { rol: Rol } | null } }
  location: { href: string }
}
// routeGuards.ts:4-7 (no exportado)

export function requireAuth({ context, location }: GuardArgs): void
// routeGuards.ts:9-13
// throw redirect({ to: '/login', search: { redirect: location.href } }) si no está autenticado.
// Usado en beforeLoad de _authenticated.tsx:8.

export function requireRole(...roles: Rol[]): (args: GuardArgs) => void
// routeGuards.ts:15-22
// Compone requireAuth + verificación de que perfil.rol esté en `roles`; si no,
// throw redirect({ to: '/' }).
// CON call sites reales — corrige lo documentado anteriormente ("sin ningún call site"):
// routes/_authenticated.admin.usuarios.tsx:6 (requireRole('admin', 'superadmin')) y
// routes/_authenticated.superadmin.empresas.tsx:6 (requireRole('superadmin')). Ambos archivos
// están fuera del alcance de esta documentación (no pertenecen a features/auth/ ni a las rutas
// listadas acá), pero se cita el call site porque depende de `perfil` estar resuelto — ver
// decisiones.md D-LOGIN-005.
```

## `features/auth/SetPasswordForm.tsx`

```typescript
export function SetPasswordForm({
  title,
  submitLabel = 'Guardar contraseña',
}: {
  title: string
  submitLabel?: string
}): JSX.Element
// SetPasswordForm.tsx:5-86
// Formulario controlado (password, confirmacion, error, isSubmitting). Valida que password ===
// confirmacion (:22-25) y minLength={8} en el input (:52). Al confirmar: supabase.auth.updateUser
// ({ password }) (:29) → supabase.auth.signOut() (:31) → navigate({ to: '/login' }) (:32).
// Reusado, sin cambios, por routes/reset-password.tsx y routes/accept-invite.tsx (solo cambian
// `title`/`submitLabel`).
```

## `features/auth/useSessionFromLink.ts`

```typescript
export function useSessionFromLink(): { checking: boolean; hasSession: boolean }
// useSessionFromLink.ts:9-30
// Espera la sesión temporal que supabase-js deja tras procesar el fragmento de la URL de un link
// de recuperación o de invitación (detectSessionInUrl, comportamiento por defecto del SDK — no
// hay código explícito en este archivo que parsee el fragmento). `checking` es true hasta que
// getSession() (o el primer evento de onAuthStateChange) resuelve; `hasSession` refleja si esa
// sesión existe. Usado por routes/reset-password.tsx y routes/accept-invite.tsx para decidir si
// mostrar SetPasswordForm o el estado "link inválido/expiró".
```

## `routes/login.tsx`

```typescript
export const Route: FileRoute<'/login'>
// login.tsx:6-11
// validateSearch: (search) => ({ redirect?: string }) — login.tsx:7-9.
// component: LoginPage (no exportado individualmente).
```

## `routes/reset-password.tsx`

```typescript
export const Route: FileRoute<'/reset-password'>
// reset-password.tsx:7-9
// Sin beforeLoad (pública). component: ResetPasswordPage (no exportado individualmente).
// ResetPasswordPage (:11-28): usa useSessionFromLink(); mientras checking → "Verificando…";
// si hasSession → <SetPasswordForm title="Elegí tu nueva contraseña" />; si no → SolicitarResetForm.
// SolicitarResetForm (:30-97, función interna, no exportada): pide email, llama
// supabase.auth.resetPasswordForEmail(email, { redirectTo: `${origin}/reset-password` }) (:41-43).
```

## `routes/accept-invite.tsx`

```typescript
export const Route: FileRoute<'/accept-invite'>
// accept-invite.tsx:5-7
// Sin beforeLoad (pública). component: AcceptInvitePage (no exportado individualmente).
// AcceptInvitePage (:9-29): usa useSessionFromLink(); mientras checking → "Verificando
// invitación…"; si hasSession → <SetPasswordForm title="Creá tu contraseña para activar tu
// cuenta" submitLabel="Activar cuenta" />; si no → mensaje de link inválido/expirado (sin acción,
// solo texto pidiendo reenvío al administrador).
```

## `routes/_authenticated.tsx`

```typescript
export const Route: FileRoute<'/_authenticated'>
// _authenticated.tsx:7-10
// beforeLoad: requireAuth (:8). component: AuthenticatedLayout (no exportado individualmente).
// AuthenticatedLayout (:12-34) agrega, frente a la versión anterior de esta doc, un useEffect
// reactivo (:16-24): si isAuthenticated pasa a false MIENTRAS el layout ya está montado (logout en
// otra pestaña, o el signOut automático de AuthContext.tsx por 401/404), navega a /login. Antes
// solo existía el chequeo de beforeLoad (una sola vez, al entrar a la ruta) — ver decisiones.md
// D-LOGIN-006.
```

## `routes/__root.tsx`

```typescript
interface RouterContext {
  auth: ReturnType<typeof useAuth>
}
// __root.tsx:4-6 (no exportado)

export const Route: RootRoute<RouterContext>
// __root.tsx:8-10
// createRootRouteWithContext<RouterContext>()({ component: () => <Outlet /> })
```

## `main.tsx` (fragmento `InnerApp`, fuera de `features/auth/` pero documentado acá)

```typescript
function InnerApp(): JSX.Element | null
// main.tsx:22-29
// const auth = useAuth() (:23)
// if (auth.loading || auth.perfilLoading) return null (:27) — antes solo esperaba auth.loading.
// return <RouterProvider router={router} context={{ auth }} /> (:28)
```
