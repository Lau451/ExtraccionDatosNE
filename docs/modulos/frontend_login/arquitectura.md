# Arquitectura — Login

## Piezas y relación entre ellas

```
  services/presupuestacion                     supabase.ts
  POST /auth/login, /auth/cambiar-password  (cliente supabase-js único:
  GET /usuarios/{id}                         setSession/getSession/onAuthStateChange/signOut)
          ▲                                            ▲
          │ lib/api/auth.ts, presupuestacionFetch      │
          │                                            │
          └────────────── AuthContext.tsx ─────────────┘
                     (AuthProvider + useAuth)
                               │
   ┌───────────────┬───────────┼───────────────────┬──────────────────────────┐
   │               │           │                   │                          │
LoginForm.tsx  routeGuards.ts  routes/login.tsx   routes/_authenticated.tsx   CambiarPasswordPage.tsx
(signIn,       (requireSession,                   (beforeLoad: requireAuth +   + CambiarPasswordForm.tsx
 username)      requireAuth,                       useEffect reactivo)         (routes/cambiar-password.tsx,
                requireRole,                                                    beforeLoad: requireSession)
                homeForRol)
```

- **`lib/api/auth.ts`** (nuevo) llama a `POST /auth/login` con `fetch` directo — sin
  `presupuestacionFetch`, para no mandar el `Authorization` de una sesión vieja
  (`auth.ts:20-21`) — y a `POST /auth/cambiar-password` con `presupuestacionFetch`.
- **`AuthContext.tsx`**: `signIn(username, password)` (`AuthContext.tsx:121-134`) obtiene la sesión
  del backend, la instala con `supabase.auth.setSession` (a partir de ahí `supabase-js` la persiste
  y la refresca como siempre) y espera `cargarPerfil`. El perfil incluye `username` y
  `debe_cambiar_password` (`:19-23`).
- **`routeGuards.ts`**: `requireSession` (solo sesión, `:12-16`), `requireAuth` (sesión + cambio
  pendiente → `/cambiar-password`, `:20-25`), `requireRole` (`:38-46`, sobre `requireAuth`) y
  `homeForRol` (`:31-36`). Recibe el estado por `context.auth`, no importa `AuthContext`.
- **`CambiarPasswordPage.tsx`/`CambiarPasswordForm.tsx`**: pantalla fuera del layout con sidebar
  (con el cambio forzado activo, el sidebar solo llevaría a rutas que rebotan de vuelta,
  comentario `CambiarPasswordPage.tsx:5-10`). La ruta usa `requireSession`, no `requireAuth`: si
  no, se redirigiría a sí misma.
- **`routes/_authenticated.tsx`**: `beforeLoad: requireAuth` cubre la entrada a cada ruta; el
  `useEffect` (`:17-29`) cubre una sesión que se cae o un perfil que pasa a tener el flag con la
  pantalla ya montada.

Ya no existen `SetPasswordForm.tsx`, `useSessionFromLink.ts`, `/reset-password` ni
`/accept-invite` (ni el mecanismo de "sesión temporal desde un link" de Supabase que usaban).

## Dónde vive el JWT y cómo llega al contexto del router

El JWT lo emite Supabase Auth, pero ahora lo pide el backend (`POST /auth/login`) y el frontend lo
recibe en el body. `AuthContext` lo entrega a `supabase.auth.setSession` (`AuthContext.tsx:126-129`)
y desde ahí `supabase-js` lo persiste y refresca según su comportamiento por defecto; no hay código
propio que escriba `localStorage`. `getSession()` y `onAuthStateChange()` (`:51-64`) mantienen
`session` en el estado de React.

El contexto tipado del router (`RouterContext`, `__root.tsx`) lo llena `main.tsx`: `InnerApp()`
llama a `useAuth()` (`main.tsx:23`), no monta el router mientras `auth.loading || auth.perfilLoading`
(`:27`) y pasa `context={{ auth }}` a `<RouterProvider>` (`:28`).

## Cambio de contraseña pendiente: frontend y backend

El flag `debe_cambiar_password` se respeta en las dos capas:

- **Frontend**: `requireAuth` y el `useEffect` de `_authenticated.tsx` mandan a `/cambiar-password`
  desde cualquier ruta protegida. Tras el cambio, `CambiarPasswordForm` llama a `refrescarPerfil()`
  (`CambiarPasswordForm.tsx:43`) y `CambiarPasswordPage` hace una navegación completa a
  `homeForRol(rol)` (`CambiarPasswordPage.tsx:31`), por el mismo motivo que D-LOGIN-007.
- **Backend**: `get_current_user` responde 403 `Debés cambiar tu contraseña antes de continuar` a
  todo salvo `GET /usuarios/{propio id}` y `POST /auth/cambiar-password` (RN-USUARIOS-035). El
  guard del frontend es comodidad de UX; la garantía real es la del backend.

## Bugs de timing corregidos (vigentes)

- **`main.tsx` esperaba solo `loading`** — ver D-LOGIN-005: `perfilLoading` evita montar el router
  con `perfil: null`.
- **Perfil inaccesible (401/404) con sesión viva → "Cargando…" infinito** — ver D-LOGIN-006:
  `signOut()` automático (`AuthContext.tsx:84-86`) + `useEffect` reactivo en `_authenticated.tsx`.
- **Redirect post-login con `router.navigate()`** — ver D-LOGIN-007: `irA` con
  `window.location.href` (`login.tsx:22-24`), también usado en `/cambiar-password`.

## Cómo se inyecta el JWT en llamadas al backend

`presupuestacionFetch` (`lib/api/presupuestacion.ts`) toma la sesión de `supabase.auth.getSession()`
y agrega `Authorization: Bearer <access_token>`. Lo usan `cargarPerfil` (`AuthContext.tsx:75`) y
`cambiarPasswordPropia` (`lib/api/auth.ts:39-45`). `iniciarSesion` es la única llamada al backend
sin ese header (endpoint público).

## Por qué no hay `estados.md`

`session: Session | null` y `perfilLoading` son binarios; `debe_cambiar_password` es un campo del
perfil, no un estado de sesión. Las transiciones se documentan en [`flujo.md`](./flujo.md).

## Dependencia hacia `services/presupuestacion`

Contratos de `POST /auth/login`, `POST /auth/cambiar-password` y `GET /usuarios/{usuario_id}` en
[`../usuarios/api.md`](../usuarios/api.md). `Rol` se redeclara en `AuthContext.tsx:9` con la misma
lista que `usuarios/models.py:7` (D-LOGIN-002).
