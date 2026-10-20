# Flujos — Login

## 1. Login exitoso (submit → `POST /auth/login` → `setSession` → perfil → redirect)

```
Usuario completa el form en LoginForm (usuario, contraseña)
        │
        ▼
handleSubmit (LoginForm.tsx:12-36) ──► signIn(username.trim(), password) (:17)
        │
        ▼
signIn (AuthContext.tsx:121-134)
  iniciarSesion(username, password) ──► POST /auth/login (lib/api/auth.ts:22-37)
        │                               el backend resuelve username → email interno y abre la sesión
        ├── 401 ──► ApiError ──► LoginForm: "Usuario o contraseña incorrectos" (RN-LOGIN-003)
        ├── 429 ──► ApiError ──► LoginForm: detail del backend, "Demasiados intentos..." (RN-LOGIN-013)
        ├── 503 (Supabase Auth caído o con 5xx) ──► "No pudimos iniciar sesión. Probá de nuevo." (RN-LOGIN-014)
        ├── otro error HTTP ──► "No pudimos iniciar sesión. Probá de nuevo."
        │
        ▼ (200 con access_token/refresh_token/user.id)
supabase.auth.setSession({ access_token, refresh_token }) (:126-130) ──► onAuthStateChange → setSession
        │
        ▼
await cargarPerfil(login.user.id) (:133) ──► GET /usuarios/{id} (:75)
        ├── éxito ──► setPerfil (incluye username y debe_cambiar_password)
        └── 401/404 ──► setPerfil(null) + signOut() automático (:84-86)
        │
        ▼
onSuccess() ──► irA(redirect ?? '/') = window.location.href (login.tsx:22-24, :40; D-LOGIN-007)
        │
        ▼
App se remonta; InnerApp espera loading/perfilLoading; beforeLoad de la ruta destino:
  requireAuth ──► si perfil.debe_cambiar_password ──► redirect a /cambiar-password (flujo 5)
  requireRole ──► si el rol no alcanza ──► homeForRol(rol)
```

`GET /usuarios/{propio id}` funciona aunque haya un cambio de contraseña pendiente
(RN-USUARIOS-035), así que el perfil siempre se resuelve tras el login. Un usuario desactivado
obtiene sesión pero el perfil responde 401 → logout automático.

## 2. Logout

```
useAuth().signOut() — botón "Cerrar sesión" del Sidebar, de Mi cuenta o de /cambiar-password,
o automático por AuthContext en 401/404 de perfil
        │
        ▼
signOut() (AuthContext.tsx:136-138) ──► supabase.auth.signOut()
        │
        ▼
onAuthStateChange con null ──► setSession(null) ──► efecto de perfil: setPerfil(null) (:96-100)
        │
        ▼
_authenticated.tsx: useEffect reactivo (_authenticated.tsx:17-29) ──► navigate({ to: '/login' })
```

Los botones manuales navegan explícitamente a `/login` tras el `signOut()`; el caso automático lo
resuelve el `useEffect` reactivo.

## 3. Acceso a ruta protegida

```
Usuario navega a una ruta bajo /_authenticated
        │
        ▼
beforeLoad: requireAuth (_authenticated.tsx:8, routeGuards.ts:20-25)
        ├── sin sesión ──► redirect({ to: '/login', search: { redirect: location.href } })
        ├── perfil.debe_cambiar_password ──► redirect({ to: '/cambiar-password' })
        └── ok ──► render (<Outlet />); si la ruta usa requireRole y el rol no alcanza
                   ──► redirect a homeForRol(rol) (routeGuards.ts:38-46)
```

`beforeLoad` corre una vez al entrar. Si la sesión se cae o el perfil pasa a tener el flag con la
pantalla ya montada, el `useEffect` de `_authenticated.tsx:17-29` redirige.

## 4. Acceso a `/login` ya autenticado

`LoginPage` (`login.tsx:26-44`) no tiene `beforeLoad`; un `useEffect` (`:30-34`) hace
`irA(redirect ?? '/')` si `isAuthenticated` ya es `true`. Si el usuario tiene un cambio pendiente,
el `requireAuth` de la ruta destino lo manda a `/cambiar-password`.

## 5. Cambio de contraseña (forzado o voluntario, `/cambiar-password`)

```
Llegada: redirect de requireAuth / useEffect (forzado), o link "Cambiar contraseña" de Mi cuenta
        │
        ▼
beforeLoad: requireSession (cambiar-password.tsx:8) — solo exige sesión
        │
        ▼
CambiarPasswordPage (CambiarPasswordPage.tsx:12-52)
  forzado = perfil.debe_cambiar_password
    ├── true  ──► texto "Tu contraseña es temporal. Tenés que cambiarla antes de continuar."; sin "Cancelar"
    └── false ──► botón "Cancelar" ──► /mi-cuenta
  "Cerrar sesión" siempre disponible (no deja al usuario atrapado)
        │
        ▼
CambiarPasswordForm.handleSubmit (CambiarPasswordForm.tsx:19-51)
  validaciones en JS (:23-36): mínimo 8, distinta de la actual, repetir coincide
        │
        ▼
cambiarPasswordPropia ──► POST /auth/cambiar-password (lib/api/auth.ts:39-45)
        ├── 422 ──► muestra el detail del backend (p. ej. "La contraseña actual es incorrecta")
        ├── 429 ──► muestra el detail del backend, "Demasiados intentos..." (RN-LOGIN-013)
        ├── 503 ──► muestra el detail del backend, "El servicio de autenticación no está disponible..." (RN-LOGIN-014)
        │
        ▼ (204)
refrescarPerfil() (:43) ──► debe_cambiar_password queda en false
        │
        ▼
onSuccess ──► irA(homeForRol(perfil.rol)) (CambiarPasswordPage.tsx:31)
```

## Flujos eliminados

Los flujos de recuperación por email (`/reset-password`) y activación de cuenta invitada
(`/accept-invite`) se eliminaron con odd/tasks/login-usuario-alta-admin.md. La recuperación ahora
la hace un admin con "Blanquear contraseña" en gestión de usuarios
(`PATCH /usuarios/{id}/password`); el usuario entra con la contraseña temporal y cae en el flujo 5.
