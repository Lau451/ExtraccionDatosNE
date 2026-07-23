# Flujos — Login

## 1. Login exitoso (submit → `signInWithPassword` → resolución de rol → redirect)

```
Usuario completa el form en LoginForm (email, password)
        │
        ▼
handleSubmit (LoginForm.tsx:12-24)
  preventDefault, setError(null), setIsSubmitting(true)
        │
        ▼
signIn(email, password) — useAuth() (AuthContext.tsx:95-98)
  await supabase.auth.signInWithPassword({ email, password })
        │
        ├── error ──► throw error ──► catch en LoginForm.tsx:19
        │                              setError('Email o contraseña incorrectos')
        │                              (ver RN-LOGIN-003)
        │
        ▼ (sin error)
onAuthStateChange dispara (AuthContext.tsx:49-53, suscripción activa desde el mount)
  setSession(newSession)
        │
        ▼
useEffect con dependencia [session, loading] (AuthContext.tsx:58-87)
  setPerfilLoading(true) (:70) ──► presupuestacionFetch<Perfil>(`/usuarios/${session.user.id}`)
                                    (AuthContext.tsx:73, ver ../usuarios/api.md)
        │
        ├── éxito ──► setPerfil(perfil resuelto) (:74)
        └── error ──► setPerfil(null) (:76); si status 401/404 ──► signOut() automático (:82-84)
        │
        ▼ (en ambos casos)
setPerfilLoading(false) (:86, finally)
        │
        ▼
onSuccess() en LoginForm (LoginForm.tsx:18) ──► navigate({ to: redirect ?? '/' })
  (login.tsx:28, RN-LOGIN-004)
```

**Nota de orden**: `onSuccess()` (y por lo tanto la navegación) se dispara apenas
`signInWithPassword` resuelve sin error, **sin esperar** a que termine la resolución de `perfil`
(ese `useEffect` corre en paralelo, disparado por el cambio de `session`). Es decir, es posible que
la navegación a la ruta protegida ocurra antes de que `perfil` esté resuelto — la ruta destino ve
`isAuthenticated: true` pero potencialmente `perfil: null` por un instante. [IMPLEMENTADO] la
secuencia descripta.

**Corrección frente a la versión anterior de esta nota**: antes se afirmaba que "ninguna guard
depende de `perfil`". Eso ya no es cierto — `requireRole` (`routeGuards.ts:15-22`) **sí** depende
de `context.auth.perfil`, y tiene call sites reales fuera del alcance de este módulo
(`routes/_authenticated.admin.usuarios.tsx:6`, `routes/_authenticated.superadmin.empresas.tsx:6`).
El bug de timing corregido en esta sesión (`perfilLoading`, ver [`decisiones.md`](./decisiones.md)
D-LOGIN-005) resuelve la carrera para el **montaje inicial del router** (carga de página/reload):
`main.tsx` no monta `RouterProvider` hasta que `perfil` también resolvió. Pero ese fix no cubre
necesariamente este flujo de login interactivo: acá el router ya está montado, y `onSuccess()`
navega de forma síncrona apenas `signInWithPassword` resuelve, sin esperar el `useEffect` de
`perfil` que dispara el cambio de `session`. [SUPOSICIÓN, no verificada en runtime en esta sesión]:
si un login exitoso redirige directamente a una ruta con `requireRole` (vía `?redirect=`), podría
existir la misma carrera que se corrigió para el reload — no se reprodujo ni se descartó
explícitamente en esta sesión. Ver [`pendientes.md`](./pendientes.md) P2 para el seguimiento.

## 2. Logout

```
useAuth().signOut() — llamado desde el botón "Cerrar sesión" del Sidebar (features/shell/Sidebar.tsx
:70-72, fuera del alcance de archivos de esta documentación) o desde Mi cuenta
(../frontend_mi_cuenta/, botón propio) o automáticamente por AuthContext.tsx en 401/404 de perfil
(ver flujo 1)
        │
        ▼
signOut() (AuthContext.tsx:100-102)
  await supabase.auth.signOut()
        │
        ▼
onAuthStateChange dispara con newSession = null (AuthContext.tsx:49-53)
  setSession(null)
        │
        ▼
useEffect [session, loading] (AuthContext.tsx:64-68)
  session es null ──► setPerfil(null), setPerfilLoading(false), return (sin llamar al backend)
        │
        ▼
_authenticated.tsx: useEffect reactivo (_authenticated.tsx:16-24)
  isAuthenticated pasó a false ──► navigate({ to: '/login' })
```

**Corrección frente a la versión anterior de esta doc**: antes se afirmaba que no había ningún
consumidor real de `signOut()` dentro ni fuera del alcance. Ahora hay al menos tres: el botón
"Cerrar sesión" del `Sidebar` (`features/shell/Sidebar.tsx:70-72`, fuera del alcance de archivos
de esta documentación pero es el más visible en la UI), el botón equivalente de Mi cuenta
(`features/mi-cuenta/MiCuenta.tsx`, documentado en
[`../frontend_mi_cuenta/`](../frontend_mi_cuenta/README.md)), y la llamada automática de
`AuthContext.tsx:83` ante un 401/404 al resolver `perfil` (ver flujo 1 y
[`decisiones.md`](./decisiones.md) D-LOGIN-006). El `useEffect` reactivo de `_authenticated.tsx`
(agregado en esta sesión) es lo que efectivamente saca al usuario de la pantalla protegida en
el caso automático — en los dos manuales, el propio componente ya navega explícitamente a
`/login` tras el `signOut()`.

## 3. Acceso a ruta protegida sin sesión

```
Usuario navega a una ruta bajo el layout /_authenticated (p. ej. "/")
        │
        ▼
beforeLoad: requireAuth (_authenticated.tsx:8, ejecuta routeGuards.ts:9-13)
        │
        ├── context.auth.isAuthenticated === true ──► continúa el render normal (<Outlet />)
        │
        └── context.auth.isAuthenticated === false
                 │
                 ▼
        throw redirect({ to: '/login', search: { redirect: location.href } })
                 │
                 ▼
        LoginPage (login.tsx) — el usuario ve el form, con `redirect` cargado en el search param
```

Esto cubre solo la entrada a la ruta (`beforeLoad` corre una vez). Si la sesión se cae *después* de
que la pantalla ya está montada, es el `useEffect` reactivo de `_authenticated.tsx:16-24` (ver
flujo 2) el que redirige — no `requireAuth`.

**Rutas con `requireRole`** (fuera del alcance de archivos de esta documentación, pero relevantes
acá): `routes/_authenticated.admin.usuarios.tsx` y `routes/_authenticated.superadmin.empresas.tsx`
agregan, sobre el mismo `beforeLoad`, la verificación de rol de `requireRole(...roles)`
(`routeGuards.ts:15-22`) — si `perfil` es `null` o su `rol` no está en la whitelist, redirige a `/`
en vez de a `/login`. Ver [`decisiones.md`](./decisiones.md) D-LOGIN-005 para el bug de timing que
esto exponía y su corrección.

## 4. Acceso a `/login` ya autenticado

```
Usuario (con sesión activa) navega a /login
        │
        ▼
LoginPage (login.tsx:13-16) lee isAuthenticated (true) y redirect (search param, si vino de un guard)
        │
        ▼
useEffect (login.tsx:18-22): isAuthenticated === true ──► navigate({ to: redirect ?? '/' })
```

Esta ruta **no** tiene un `beforeLoad` propio (a diferencia de `_authenticated.tsx`) — el redirect
en caso de ya estar autenticado ocurre client-side, después del render inicial, vía `useEffect`, no
antes de renderizar. [IMPLEMENTADO] — confirmado leyendo `login.tsx` completo: no hay `beforeLoad`
en la definición de la ruta (`login.tsx:6-11`).

## 5. Recuperación de contraseña (`/reset-password`)

```
Usuario navega a /reset-password (sin sesión) ──► click "¿Olvidaste tu contraseña?" en LoginForm
        │
        ▼
useSessionFromLink() (reset-password.tsx:12) ──► checking: true, hasSession: false (estado inicial)
        │
        ▼
getSession() resuelve sin sesión ──► checking: false, hasSession: false
        │
        ▼
SolicitarResetForm (reset-password.tsx:30-97): usuario ingresa email
        │
        ▼
supabase.auth.resetPasswordForEmail(email, { redirectTo: `${origin}/reset-password` })
  (reset-password.tsx:41-43)
        │
        ▼
"Si el email existe, te enviamos un link" (mensaje genérico, no confirma si el email existe)
        │
        ▼
Usuario abre el link del mail ──► vuelve a /reset-password con fragmento de sesión temporal
        │
        ▼
useSessionFromLink() detecta la sesión (onAuthStateChange/getSession) ──► hasSession: true
        │
        ▼
<SetPasswordForm title="Elegí tu nueva contraseña" /> (reset-password.tsx:21)
        │
        ▼
handleSubmit (SetPasswordForm.tsx:18-38): valida password === confirmacion (:22-25)
  ──► supabase.auth.updateUser({ password }) (:29)
  ──► supabase.auth.signOut() (:31)
  ──► navigate({ to: '/login' }) (:32)
```

El usuario tiene que loguearse de nuevo con la contraseña nueva — `SetPasswordForm` no deja al
usuario autenticado tras el cambio (hace `signOut()` explícito). [IMPLEMENTADO].

## 6. Activación de cuenta invitada (`/accept-invite`)

Mismo mecanismo que el flujo 5, con dos diferencias: el link lo genera el backend al invitar (ver
`docs/modulos/usuarios/` — `redirect_to` construido con `frontend_url` de `core/config.py`, fila
`RN-CORE` correspondiente en `../core/reglas.md`), y no hay pantalla de "pedir el link" — si no hay
sesión temporal, `accept-invite.tsx:21-24` muestra directamente un mensaje de link inválido/
expirado, sin ninguna acción de reenvío propia (el reenvío, si existe, lo hace un admin desde
`usuarios/`, fuera del alcance de esta documentación).

```
Usuario abre el link de invitación ──► /accept-invite con fragmento de sesión temporal
        │
        ▼
useSessionFromLink() (accept-invite.tsx:10)
        │
        ├── hasSession: true ──► <SetPasswordForm title="Creá tu contraseña para activar tu
        │                          cuenta" submitLabel="Activar cuenta" /> (accept-invite.tsx:19)
        │                          ──► mismo handleSubmit del flujo 5 ──► /login
        │
        └── hasSession: false ──► mensaje fijo "Este link de invitación no es válido o ya
                                    expiró..." (accept-invite.tsx:21-24), sin acción disponible
```
