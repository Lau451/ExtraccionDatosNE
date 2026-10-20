# Reglas — Login

El módulo es mayormente mecánico (formularios + llamadas al backend y a `supabase-js`). Se
documentan solo las reglas verificadas contra el código de la rama `feat/login-usuario-alta-admin`.
RN-LOGIN-007 y 008 quedaron **[ELIMINADAS]** con `/reset-password` y `SetPasswordForm`; se conserva
el número, no se renumera.

### RN-LOGIN-001 — **[MODIFICADA]** Validación de formulario: solo la nativa del navegador

- **Regla**: los campos "Usuario" y "Contraseña" son `required` (`LoginForm.tsx:41-69`); el de
  usuario es `type="text"` con `autoCapitalize="none"` y `autoComplete="username"`. No hay
  validación de formato en JavaScript: el formato (3-30 caracteres `a-z 0-9 . _ -`) lo valida el
  backend, que ante un formato inválido devuelve el mismo 401 genérico (RN-USUARIOS-031/038). El
  frontend solo hace `trim()` (`:17`); la conversión a minúsculas la hace el backend.
- [IMPLEMENTADO]

### RN-LOGIN-002 — **[MODIFICADA]** Login solo por nombre de usuario y contraseña, vía backend

- **Regla**: la única vía de autenticación es `POST /auth/login` (`lib/api/auth.ts:22-37`), cuya
  sesión se instala con `supabase.auth.setSession` (`AuthContext.tsx:126-129`). No hay
  `signInWithPassword`, OAuth ni magic link en el frontend. El email de Supabase Auth nunca llega al
  navegador.
- [IMPLEMENTADO]. Cubierto por `lib/api/auth.test.ts` y `AuthContext.test.tsx`.

### RN-LOGIN-003 — **[MODIFICADA]** Error de login: "Usuario o contraseña incorrectos" para 401, genérico para el resto

- **Regla**: `LoginForm` muestra `'Usuario o contraseña incorrectos'` si el error es un 401 o no es
  un `ApiError` (por ejemplo, un error de `setSession`), y `'No pudimos iniciar sesión. Probá de
  nuevo.'` para cualquier otro `ApiError` salvo el 429 (`LoginForm.tsx:26-32`; el 429 sigue
  RN-LOGIN-013). Siempre hace `console.error` del
  error original (`:20`). El backend devuelve el mismo 401 para usuario inexistente y contraseña
  incorrecta, así que no se pueden sondear usernames.
- [IMPLEMENTADO]. Cubierto por `LoginForm.test.tsx`.

### RN-LOGIN-004 — Redirect post-login respeta `?redirect=`, con `/` como default

- **Regla**: `/login` acepta `redirect` (`login.tsx:7-9`); tras el login, `irA(redirect ?? '/')`
  (`login.tsx:40`), también si ya hay sesión al entrar (`:30-34`). Un rol sin acceso a `/` rebota a
  `homeForRol(rol)` (RN-LOGIN-006); con cambio pendiente, a `/cambiar-password` (RN-LOGIN-011).
- [IMPLEMENTADO]

### RN-LOGIN-005 — **[MODIFICADA]** Guard de ruta protegida: sin sesión → `/login` con el destino original

- **Regla**: `requireSession` (`routeGuards.ts:12-16`) lanza
  `redirect({ to: '/login', search: { redirect: location.href } })` si no hay sesión. `requireAuth`
  (`:20-25`) la compone y agrega el chequeo de RN-LOGIN-011.
- [IMPLEMENTADO]

### RN-LOGIN-006 — `requireRole` restringe por rol, redirect a la home del rol si no alcanza

- **Regla**: `requireRole(...roles)` (`routeGuards.ts:38-46`) corre `requireAuth` y exige
  `perfil.rol` en la whitelist; si no, `redirect({ to: homeForRol(rol) })`. `homeForRol`
  (`:31-36`): `/` para `CARGA_DOCUMENTOS_ROLES`, `/productos` para `compras`,
  `/superadmin/empresas` para `superadmin`, `/mi-cuenta` sin perfil.
- [IMPLEMENTADO]. Cubierto por `routeGuards.test.ts`.

### RN-LOGIN-007 — **[ELIMINADA]** Recuperación de contraseña con mensaje genérico

- Eliminada junto con `/reset-password` (odd/tasks/login-usuario-alta-admin.md S4). No hay
  recuperación por email: el login muestra "¿Olvidaste tu contraseña? Contactá al administrador
  para que te la blanquee." (`LoginForm.tsx:81-83`).

### RN-LOGIN-008 — **[ELIMINADA]** `SetPasswordForm`

- Eliminada junto con `SetPasswordForm.tsx`, `/reset-password` y `/accept-invite`. La reemplaza
  RN-LOGIN-012 (`CambiarPasswordForm`).

### RN-LOGIN-009 — Logout automático si el fetch de `perfil` falla con 401 o 404

- **Regla**: si `GET /usuarios/{id}` falla con `ApiError` 401 (usuario desactivado) o 404 (fila
  borrada), `AuthContext` llama a `supabase.auth.signOut()` (`AuthContext.tsx:84-86`). Un 403 por
  cambio de contraseña pendiente no aplica a este endpoint (está exceptuado sobre el propio id).
- **Consecuencia**: con el `useEffect` de `_authenticated.tsx:17-29`, el usuario termina en
  `/login`.
- [IMPLEMENTADO]

### RN-LOGIN-010 — El router no se monta hasta que `perfil` también resolvió (`perfilLoading`)

- **Regla**: `AuthContext` no resuelve `perfil` hasta que `loading` sea `false`
  (`AuthContext.tsx:94`) y expone `perfilLoading`; `main.tsx:27` no monta el router mientras
  `auth.loading || auth.perfilLoading`.
- [IMPLEMENTADO]. Ver D-LOGIN-005.

### RN-LOGIN-011 — **[NUEVA]** Con `debe_cambiar_password`, toda ruta protegida manda a `/cambiar-password`

- **Regla**: `requireAuth` lanza `redirect({ to: '/cambiar-password' })` si
  `perfil.debe_cambiar_password` (`routeGuards.ts:20-25`); como `requireRole` se compone sobre
  `requireAuth`, aplica a todas las rutas de negocio. `_authenticated.tsx:17-29` lo repite de forma
  reactiva con la pantalla ya montada. `/cambiar-password` usa `requireSession` para no
  redirigirse a sí misma (`cambiar-password.tsx:5-8`).
- **Consecuencia**: el usuario con contraseña temporal solo ve `/cambiar-password` (con "Cerrar
  sesión"). El backend aplica el mismo bloqueo con 403 (RN-USUARIOS-035).
- [IMPLEMENTADO]. Cubierto por `routeGuards.test.ts` y `cambiarPasswordRoute.test.ts`.

### RN-LOGIN-012 — **[NUEVA]** `CambiarPasswordForm`: mínimo 8, distinta de la actual, confirmación igual

- **Regla**: antes de llamar al backend (`CambiarPasswordForm.tsx:23-36`): nueva de menos de 8 →
  "La contraseña nueva debe tener al menos 8 caracteres"; nueva igual a la actual → "La contraseña
  nueva tiene que ser distinta de la actual"; nueva distinta de la confirmación → "Las contraseñas
  no coinciden". El backend vuelve a validar (RN-USUARIOS-039) y su `detail` se muestra tal cual
  (`:47`), p. ej. "La contraseña actual es incorrecta" (422, no 401: no desloguea).
- **Resultado**: tras el 204, `refrescarPerfil()` y navegación completa a `homeForRol(rol)`. A
  diferencia del viejo `SetPasswordForm`, no hace `signOut()`: el usuario sigue logueado.
- [IMPLEMENTADO]. Cubierto por `CambiarPasswordPage.test.tsx`.

### RN-LOGIN-013 — **[NUEVA]** Un 429 del backend muestra su propio mensaje en login y cambio de contraseña

- **Regla**: si `POST /auth/login` responde 429, `LoginForm` muestra el `detail` del backend tal
  cual (`error.message`, `LoginForm.tsx:24-25`) en vez de "Usuario o contraseña incorrectos". En
  `CambiarPasswordForm` el 429 de `POST /auth/cambiar-password` sale por el mismo camino que
  cualquier `ApiError`: se muestra su `detail` (`CambiarPasswordForm.tsx:47`). El texto lo define
  el backend: "Demasiados intentos. Probá de nuevo en unos minutos." (RN-USUARIOS-043). En ningún
  caso se navega ni se llama a `onSuccess`.
- **Motivo**: el límite de intentos de Supabase Auth lo comparten todos los usuarios (el sign-in
  sale del backend); mostrarlo como credenciales inválidas confundía al usuario
  (odd/tasks/login-usuario-alta-admin.md S8).
- [IMPLEMENTADO] (commit `0c8052c`). Cubierto por `LoginForm.test.tsx` ("un 429 muestra el mensaje
  de demasiados intentos del backend", y "un 500 sigue mostrando el mensaje genérico de
  reintento") y `CambiarPasswordPage.test.tsx` ("un 429 muestra el mensaje de demasiados intentos
  y no navega").

### RN-LOGIN-014 — **[NUEVA]** Supabase Auth caído: el backend responde 503 y el frontend muestra su `detail`

- **Regla**: si Supabase Auth no responde o responde 5xx, `POST /auth/login` y
  `POST /auth/cambiar-password` responden 503 `El servicio de autenticación no está disponible.
  Probá de nuevo en unos minutos.` (RN-USUARIOS-047). `LoginForm` muestra ese `detail` igual que el
  del 429 (`LoginForm.tsx:25-26`); un 500 sigue mostrando `'No pudimos iniciar sesión. Probá de
  nuevo.'` (RN-LOGIN-003). `CambiarPasswordForm` muestra el `detail`
  del backend como con cualquier `ApiError` (`CambiarPasswordForm.tsx:47`). En ningún caso se
  navega ni se llama a `onSuccess`.
- **Motivo**: antes una caída de Auth salía como 500 o como "credenciales incorrectas"
  (odd/tasks/login-usuario-alta-admin.md S12).
- [IMPLEMENTADO] backend (commit `34bcc44`) y `LoginForm` (test "un 503 muestra el mensaje de
  servicio no disponible del backend" en `LoginForm.test.tsx`).
