# Reglas — Login

El módulo es mayormente mecánico (formularios + llamadas al SDK de Supabase), pero ya no es tan
chico como cuando solo cubría login: ahora también resuelve recuperación de contraseña, activación
de cuenta invitada, y el orden de resolución de sesión/perfil que consumen las guards de rol. Se
documentan solo las reglas verificadas contra el código; no se infla la lista con comportamiento
genérico de HTML/React que no sea una decisión del módulo.

### RN-LOGIN-001 — Validación de formulario: solo la nativa del navegador

- **Regla**: los campos `email` y `password` son `required` y el de email es `type="email"`
  (`LoginForm.tsx:33-34`, `:48-49`), pero no hay ninguna validación adicional en JavaScript (sin
  regex de formato, sin mínimo de longitud de contraseña, sin validación de dominio). Toda la
  validación de formato depende de la validación nativa del navegador sobre esos atributos HTML.
- **Consecuencia**: un email con formato inválido según el navegador nunca llega a `handleSubmit`
  (el navegador bloquea el submit); un email sintácticamente válido pero inexistente sí llega, y el
  error se resuelve recién en la respuesta de `signInWithPassword` (ver RN-LOGIN-003).
- [IMPLEMENTADO]

### RN-LOGIN-002 — Login solo por email/contraseña, sin proveedores externos

- **Regla**: la única vía de autenticación implementada es `supabase.auth.signInWithPassword`
  (`AuthContext.tsx:61`). No hay ningún código en el alcance de esta documentación que use OAuth,
  magic link, o cualquier otro método de `supabase-js`.
- [IMPLEMENTADO]

### RN-LOGIN-003 — Cualquier error de `signIn` se muestra como "Email o contraseña incorrectos"

- **Regla**: `LoginForm.tsx` captura cualquier excepción de `signIn` con un `catch` genérico y
  siempre muestra el mismo mensaje, `'Email o contraseña incorrectos'` (`LoginForm.tsx:18-19`), sin
  distinguir el motivo real del error (credenciales inválidas, red caída, rate limit de Supabase,
  etc.).
- **Consecuencia**: el mensaje es correcto para el caso más común (credenciales inválidas), pero es
  potencialmente engañoso si el error real es de otra naturaleza (por ejemplo, el servicio de
  Supabase Auth no responde). No hay `console.error` ni logging del error original en este archivo.
- [IMPLEMENTADO]

### RN-LOGIN-004 — Redirect post-login respeta `?redirect=`, con `/` como default

- **Regla**: la ruta `/login` acepta un search param `redirect` (validado como `string | undefined`
  en `login.tsx:7-9`). Al loguearse exitosamente, `LoginForm` navega a `redirect ?? '/'`
  (`login.tsx:28`, vía la prop `onSuccess` pasada desde `LoginPage`). Si el usuario ya está
  autenticado y visita `/login` directamente, el mismo destino se resuelve en un `useEffect`
  (`login.tsx:18-22`).
- **Default `/` y roles sin carga de documentos**: `/` (`routes/_authenticated.index.tsx:8`) tiene
  guard `requireRole(...CARGA_DOCUMENTOS_ROLES)` desde la matriz de roles
  (odd/tasks/roles-permisos-matriz.md S9). Un `compras` o `superadmin` que cae en el default `/`
  es rebotado por ese guard a `homeForRol(rol)` (RN-LOGIN-006): `/productos` o
  `/superadmin/empresas`.
- **Origen del `redirect`**: lo establece `requireAuth` al rechazar el acceso a una ruta protegida,
  usando la URL completa de destino (`location.href`, `routeGuards.ts:12`).
- [IMPLEMENTADO]

### RN-LOGIN-005 — Guard de ruta protegida: sin sesión, redirect a `/login` con el destino original

- **Regla**: `requireAuth` lanza `redirect({ to: '/login', search: { redirect: location.href } })`
  si `context.auth.isAuthenticated` es falso (`routeGuards.ts:10-14`). No hay ninguna otra condición
  (no depende de `perfil`, solo de `isAuthenticated`). Corre una sola vez, en `beforeLoad`, al
  entrar a la ruta — ver RN-LOGIN-009 para el caso de sesión que se cae después.
- [IMPLEMENTADO]

### RN-LOGIN-006 — `requireRole` restringe por rol, redirect a la home del rol (no a `/login`) si no alcanza

- **Regla**: `requireRole(...roles: Rol[])` (`routeGuards.ts:27-35`) primero corre `requireAuth`
  (mismo comportamiento que RN-LOGIN-005 si no hay sesión) y, si hay sesión, exige que
  `context.auth.perfil` no sea `null` y que `perfil.rol` esté en la whitelist recibida; si no,
  `throw redirect({ to: homeForRol(rol) })` (`routeGuards.ts:30-32`) — a diferencia de
  `requireAuth`, no manda a `/login`, manda a la pantalla de aterrizaje del rol.
- **Home por rol** (`homeForRol`, `routeGuards.ts:20-25`, matriz de roles S9): `/` para
  `admin`/`gerencia`/`lider_comercial`/`comercial` (`CARGA_DOCUMENTOS_ROLES`), `/productos` para
  `compras`, `/superadmin/empresas` para `superadmin`, y `/mi-cuenta` (sin guard de rol) si no hay
  perfil resuelto. Antes redirigía siempre a `/`; como `/` ahora tiene guard de rol propio, eso
  haría un loop para `compras`/`superadmin`.
- **Corrección frente a la versión anterior de esta documentación**: esta regla existía en el
  código pero no se numeraba porque se creía sin call sites. Hoy la usan todas las rutas de
  negocio de `routes/_authenticated.*.tsx` (fuera del alcance de archivos de este módulo), entre
  ellas `routes/_authenticated.admin.usuarios.tsx:7`, `routes/_authenticated.superadmin.empresas.tsx:6`
  y `routes/_authenticated.index.tsx:8`.
- [IMPLEMENTADO]. Depende de que `perfil` esté resuelto en el momento en que corre `beforeLoad` —
  ver RN-LOGIN-010 sobre cómo se garantiza eso en la carga inicial.

### RN-LOGIN-007 — Recuperación de contraseña: mensaje de éxito genérico, no confirma si el email existe

- **Regla**: `SolicitarResetForm` (`reset-password.tsx:30-97`) muestra el mismo mensaje de éxito
  ("Si el email existe en el sistema, te enviamos un link...", `reset-password.tsx:53-58`)
  independientemente de si `supabase.auth.resetPasswordForEmail` encontró o no una cuenta con ese
  email — no hay ninguna rama de "email no encontrado" en el código del frontend.
- **Consecuencia**: evita que un atacante use el formulario para enumerar emails registrados en el
  sistema.
- [IMPLEMENTADO]. Nota: esto depende de que el propio Supabase Auth no filtre esa información por
  otra vía (tiempo de respuesta, etc.) — no verificado en esta sesión, fuera del alcance del código
  del frontend.

### RN-LOGIN-008 — `SetPasswordForm`: contraseña nueva y confirmación deben coincidir, mínimo 8 caracteres

- **Regla**: `SetPasswordForm` (reusado por `/reset-password` y `/accept-invite`) valida
  `password === confirmacion` en JavaScript antes de llamar a Supabase (`SetPasswordForm.tsx:22-25`,
  mensaje "Las contraseñas no coinciden"); el input de contraseña tiene `minLength={8}`
  (`SetPasswordForm.tsx:52`), validado por el navegador (mismo patrón que RN-LOGIN-001: sin regex
  de complejidad adicional en JS).
- **Resultado**: tras confirmar, `updateUser({ password })` → `signOut()` → `navigate('/login')`
  (`SetPasswordForm.tsx:29-32`) — el usuario no queda logueado con la contraseña nueva, tiene que
  volver a entrar.
- [IMPLEMENTADO]

### RN-LOGIN-009 — Logout automático si el fetch de `perfil` falla con 401 o 404

- **Regla**: si `presupuestacionFetch<Perfil>('/usuarios/{id}')` falla con una `ApiError` cuyo
  `status` es 401 (usuario desactivado, ver RN-CORE-026 en `../core/reglas.md`) o 404 (fila
  borrada), `AuthContext.tsx` llama a `supabase.auth.signOut()` automáticamente
  (`AuthContext.tsx:75-84`), sin esperar ninguna acción del usuario.
- **Consecuencia**: combinado con el `useEffect` reactivo de `_authenticated.tsx:16-24`, un usuario
  desactivado o borrado del lado del backend se desloguea y es redirigido a `/login` la próxima vez
  que `AuthContext` intente resolver su `perfil` — sin este mecanismo, la UI quedaba mostrando un
  estado de carga indefinido (bug corregido en esta sesión, ver
  [`decisiones.md`](./decisiones.md) D-LOGIN-006).
- [IMPLEMENTADO]

### RN-LOGIN-010 — El router no se monta hasta que `perfil` también resolvió (`perfilLoading`)

- **Regla**: `AuthContext.tsx` no empieza a resolver `perfil` hasta que `loading` (resolución de
  sesión) sea `false` (`AuthContext.tsx:62`), y expone ese segundo estado como `perfilLoading`
  (`:23`, `:41`). `main.tsx` (`InnerApp`) no monta `<RouterProvider>` mientras `auth.loading ||
  auth.perfilLoading` sea `true` (`main.tsx:27`).
- **Consecuencia**: cualquier guard que dependa de `context.auth.perfil` (como `requireRole`, ver
  RN-LOGIN-006) ve un valor ya resuelto la primera vez que corre `beforeLoad`, incluso en un
  reload/deep-link directo a una ruta protegida por rol.
- [IMPLEMENTADO]. Corrige el bug de timing encontrado y reproducido en esta sesión — ver
  [`decisiones.md`](./decisiones.md) D-LOGIN-005. No cubre necesariamente el caso de un login
  interactivo que redirige de inmediato a una ruta con `requireRole` sin recargar la página — ver
  la nota en [`flujo.md`](./flujo.md) #1 y [`pendientes.md`](./pendientes.md).
