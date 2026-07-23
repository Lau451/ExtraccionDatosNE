# Decisiones de diseño — Login

Numeración D-LOGIN-NNN, verificada contra el código y el proposal archivado
(`openspec/changes/archive/login-frontend/proposal.md`).

### D-LOGIN-001 — Resolver el rol con un `GET` adicional en vez de un claim JWT custom

- **Decisión**: `AuthContext.tsx` no lee `rol` del JWT de Supabase; lo resuelve con
  `presupuestacionFetch<Perfil>(`/usuarios/${session.user.id}`)` (`AuthContext.tsx:55`) en un
  `useEffect` que corre cada vez que cambia `session` (`AuthContext.tsx:48-58`).
- **Motivo**: explícito en un comentario del propio código (`AuthContext.tsx:53-54`): "El JWT de
  Supabase no trae el rol como claim — se resuelve con el mismo GET que ya usa el backend en
  core/auth.py (SELECT a `usuarios` vía RLS)". El proposal original agrega contexto de la decisión
  de implementación (`proposal.md:46-50`): se evaluó primero un `SELECT` directo a la tabla
  `usuarios` desde `supabase-js`, pero esa opción fue bloqueada explícitamente por el usuario del
  proyecto durante la implementación, pidiendo verificar antes si ya existía un endpoint
  `/usuarios/{id}` o `/me` en el backend — existía, y se reusó tal cual sin crear nada nuevo.
- **Ventajas**: coherente con la decisión más amplia de que "todo dato de negocio pasa por los
  backends, que ya aplican RLS y lógica de dominio" (`proposal.md:23-24`) — el frontend no duplica
  la política de acceso a `usuarios` que ya vive en `services/presupuestacion`; reusa un endpoint
  existente sin agregar superficie nueva de backend.
- **Desventajas**: un round-trip HTTP adicional en cada carga/cambio de sesión antes de tener el
  rol disponible (ver la nota de orden en [`flujo.md`](./flujo.md) #1). El proposal lo reconoce
  como el único riesgo del scope y lo acepta explícitamente: "es un solo GET, cacheable si hiciera
  falta más adelante" (`proposal.md:55-56`).

### D-LOGIN-002 — `Rol` se redeclara en el frontend en vez de compartir el tipo con el backend

- **Decisión**: `AuthContext.tsx:6` define su propio `type Rol` con los 6 mismos valores literales
  que `usuarios/models.py:5` del backend (`services/presupuestacion`), sin ningún mecanismo de
  generación o import compartido entre ambos proyectos.
- **Motivo**: no documentado explícitamente en el código ni en el proposal — Motivo pendiente de
  definición.
- **Ventajas**: cada proyecto (`frontend/`, `services/presupuestacion/`) puede evolucionar sin
  acoplamiento de build entre sí; no requiere una librería compartida de tipos ni un paso de
  generación de tipos desde el backend.
- **Desventajas**: los dos `Literal`/union quedan sincronizados solo por disciplina manual — si el
  backend agrega o renombra un rol en `usuarios/models.py`, nada falla en build ni en runtime en el
  frontend hasta que alguien note la divergencia. Ver [`pendientes.md`](./pendientes.md).

### D-LOGIN-003 — `requireRole` se implementa sin usarse todavía [SUPERADA POR EL CÓDIGO — ver nota]

- **Decisión original**: `routeGuards.ts:15-22` define `requireRole(...roles: Rol[])` compuesto
  sobre `requireAuth`, sin que ninguna ruta del MVP lo invocara al momento de escribir esta
  decisión.
- **Motivo original**: explícito en el proposal archivado (`proposal.md:35-36`): "se dejó la
  función armada pero sin ningún call site, porque ninguna ruta actual del MVP la necesita
  todavía", listado bajo "Explícitamente fuera de scope".
- **Nota de esta sesión — el hecho que motivaba la decisión ya no es cierto**: `requireRole` **sí
  tiene call sites reales** ahora: `routes/_authenticated.admin.usuarios.tsx:6`
  (`requireRole('admin', 'superadmin')`) y `routes/_authenticated.superadmin.empresas.tsx:6`
  (`requireRole('superadmin')`) — confirmado por grep y lectura directa en esta sesión. Ambos
  archivos están fuera del alcance de este módulo (pertenecen a `gestion-usuarios/` y
  `gestion-empresas/`), por eso no se documentan acá en detalle, pero el hecho de que existan
  invalida la premisa de D-LOGIN-003 y es la causa raíz por la que el bug de timing documentado en
  D-LOGIN-005 era observable: sin esos call sites, nadie leía `context.auth.perfil` al montar el
  router, y el bug no se habría manifestado. Se conserva el registro de la decisión original por
  trazabilidad histórica, marcada como superada; no se retira el ítem P2(1) de
  [`pendientes.md`](./pendientes.md), que ahora describe un riesgo real (código con call sites pero
  sin test) en vez de un riesgo hipotético.

### D-LOGIN-004 — Registro y recuperación de contraseña quedan fuera de scope [SUPERADA — ver D-LOGIN-005/006 y `/reset-password`, `/accept-invite`]

- **Decisión original**: no había implementación de `supabase.auth.signUp` ni de
  `supabase.auth.resetPasswordForEmail` en ningún archivo de `frontend/src/` al momento de escribir
  esta decisión.
- **Motivo original**: explícito en el proposal archivado, sección "Explícitamente fuera de scope"
  (`proposal.md:33-34`): "Registro de usuarios nuevos" y "Recuperación/reset de contraseña" se
  listaban ambos como fuera de scope del MVP.
- **Qué la reemplaza**: en esta sesión se confirmó que **la recuperación de contraseña ya está
  implementada**: `routes/reset-password.tsx` (`SolicitarResetForm`, `:30-97`) llama a
  `supabase.auth.resetPasswordForEmail` (`:41-43`); el link resultante deja una sesión temporal que
  habilita `SetPasswordForm` (`features/auth/SetPasswordForm.tsx`) vía el hook compartido
  `useSessionFromLink` (`features/auth/useSessionFromLink.ts`). El mismo mecanismo se reusa para
  activar una cuenta invitada en `routes/accept-invite.tsx`. El registro libre de usuarios
  (`signUp`) sigue sin implementarse — el alta la hace un admin/superadmin desde `usuarios/`
  (`invitarUsuario`, `lib/api/usuarios.ts:41-47`) y el invitado activa vía `/accept-invite`, no vía
  auto-registro — esa mitad de la decisión original sigue vigente.
- **Ventajas** (de la decisión original, contexto histórico): redujo el alcance del MVP a lo mínimo
  indispensable para desbloquear pantallas que dependían de `services/presupuestacion`
  (`proposal.md:9-13`).
- **Desventajas que ya no aplican**: la falta de autoservicio para recuperar contraseña — el ítem
  correspondiente de [`pendientes.md`](./pendientes.md) P2(3) queda resuelto y se retira en esta
  sesión.

### D-LOGIN-005 — Esperar `perfilLoading` (no solo `loading`) antes de montar el router

- **Decisión**: `AuthContext.tsx` expone un segundo flag, `perfilLoading` (`AuthContext.tsx:23`,
  `:41`), secuenciado explícitamente para no arrancar la resolución de `perfil` hasta que `loading`
  sea `false` (`:62`). `main.tsx` (`InnerApp`) espera `auth.loading || auth.perfilLoading` antes de
  montar `<RouterProvider>` (`main.tsx:27`), en vez de esperar solo `auth.loading` como antes.
- **Motivo**: bug real encontrado y reproducido en esta sesión (confirmado en vivo con Chrome):
  `requireRole()` (`routeGuards.ts:15-22`, con call sites reales — ver corrección de D-LOGIN-003)
  depende de `context.auth.perfil`, que se resuelve en un segundo paso asíncrono aparte de la
  sesión. Sin esperar ese segundo paso, un reload directo (deep-link) a una ruta con `requireRole`
  (p. ej. `/admin/usuarios`) rebotaba a `/` aunque el usuario tuviera el rol correcto, porque el
  router se montaba y corría `beforeLoad` con `perfil` todavía `null`.
- **Ventajas**: elimina la carrera por completo — el router nunca se monta con `perfil` en un
  estado transitorio. Es la corrección más directa dado que la causa era exactamente esa carrera.
- **Desventajas**: agrega un frame más de espera (pantalla en blanco, `main.tsx:27` devuelve
  `null`) entre "sesión resuelta" y "app montada" en cada carga — antes esa espera cubría solo
  `loading`, ahora cubre `loading` y `perfilLoading` combinados. No se midió el impacto perceptible
  en esta sesión.
- **Nota — esta decisión sola NO alcanzó para el caso login→redirect**: cubre el reload directo
  (deep-link) a una ruta con `requireRole`, pero NO el caso "loguearse y navegar sin recargar la
  página" — ver D-LOGIN-007, encontrado y corregido en la misma sesión, después de esta decisión.

### D-LOGIN-007 — Redirect post-login usa `window.location.href` (hard navigation), no `router.navigate()`

- **Decisión**: `routes/login.tsx` reemplazó `navigate({ to: redirect ?? '/' })` (de
  `@tanstack/react-router`) por una función `irA(destino)` que hace `window.location.href = destino`
  (`login.tsx:20-22`, usada en `:31` y en el `onSuccess` de `LoginForm` en `:38`).
- **Motivo**: tercer bug real de timing encontrado y reproducido en esta sesión, DESPUÉS de aplicar
  D-LOGIN-005/006. Con esos dos fixes ya aplicados, el caso "reload directo a una ruta protegida"
  funcionaba, pero el caso "loguearse y ser redirigido a esa misma ruta sin recargar la página"
  seguía fallando — reproducido en vivo: login con un superadmin real y `?redirect=/superadmin/empresas`
  aterrizaba en `/` en vez de en la ruta pedida, aunque el rol ya era correcto.
  Causa raíz distinta de D-LOGIN-005: `signIn()` (`AuthContext.tsx`) ya esperaba a que `cargarPerfil`
  terminara (incluyendo el `await fetch` y el `setPerfil(...)`) antes de resolver su propia promesa,
  pero `setPerfil` es una actualización de estado de React — asíncrona respecto al código que sigue.
  `LoginForm` llamaba a `onSuccess()` → `navigate(...)` inmediatamente después de que `signIn()`
  resolvía, y en ese instante el componente `InnerApp` (`main.tsx`) todavía no había vuelto a
  renderizar con el `perfil` nuevo — por lo tanto el `context={{auth}}` que recibía el
  `RouterProvider`, y de ahí `requireRole()` en `beforeLoad`, seguía viendo `perfil: null`.
  Esperar la promesa de `signIn()` no alcanza porque lo que hace falta esperar no es el fetch sino
  el re-render de React, que no tiene una promesa asociada.
- **Ventajas**: elimina la clase entera de carreras entre el estado de React y el `context` del
  router — un hard navigation fuerza que la app se remonte desde cero, y `InnerApp` ya garantiza
  (por D-LOGIN-005) que el router no se monta hasta que `loading`/`perfilLoading` estén resueltos.
  Es la misma garantía que ya funcionaba para el caso "reload directo", aplicada también al caso
  "redirect post-login".
- **Desventajas**: pierde el beneficio de SPA (sin flash de página completa) específicamente en la
  transición login→destino — un costo aceptado a cambio de simplicidad y de no tener que sincronizar
  manualmente el `context` del router con React vía `router.invalidate()`/`router.update()` (opción
  más "correcta" en teoría, no implementada por no ser necesaria una vez aceptado el trade-off).
  Se aplicó también al `useEffect` de `LoginPage` que redirige si `isAuthenticated` ya es `true` al
  entrar a `/login` (`login.tsx:29-33`), por la misma razón, aunque ese camino no se reprodujo en
  vivo con el mismo detalle que el de `onSuccess`.

### D-LOGIN-006 — Logout automático en 401/404 de perfil + guard reactivo en `_authenticated.tsx`

- **Decisión**: dos cambios relacionados, ambos motivados por el mismo bug:
  1. `AuthContext.tsx` llama a `supabase.auth.signOut()` automáticamente si el fetch de `perfil`
     falla con `ApiError.status` 401 o 404 (`AuthContext.tsx:75-84`).
  2. `routes/_authenticated.tsx` (`AuthenticatedLayout`) agrega un `useEffect` reactivo
     (`_authenticated.tsx:16-24`) que redirige a `/login` si `isAuthenticated` pasa a `false`
     mientras la pantalla ya está montada.
- **Motivo**: segundo bug real encontrado y reproducido en esta sesión. Si el fetch de `perfil`
  fallaba con 401 (usuario desactivado — ver `core/auth.py` `get_current_user`, RN-CORE-026 en
  `../core/reglas.md`) o 404 (fila de usuario borrada) mientras la sesión de Supabase seguía
  técnicamente viva, la UI quedaba mostrando "Cargando…" para siempre en el `Sidebar`: sin el
  `signOut()` automático, nada bajaba `isAuthenticated` a `false`; y sin el `useEffect` reactivo en
  `_authenticated.tsx`, aunque `isAuthenticated` cambiara, el guard `requireAuth` (que solo corre
  una vez, en `beforeLoad`, al entrar a la ruta) nunca se re-evaluaba para sacar al usuario de la
  pantalla ya montada.
- **Ventajas**: cierra el círculo completo — un usuario desactivado o borrado del lado del backend
  ahora sí se desloguea y redirige, sin quedar en un estado de carga infinita indefinidamente.
- **Desventajas**: el `signOut()` automático se dispara para *cualquier* 401/404 de ese endpoint
  específico, no solo para "usuario desactivado" — un 404 transitorio de red mal interpretado (poco
  probable dado que `presupuestacionFetch` solo lanza `ApiError` con el `status` real de la
  respuesta, `lib/api/presupuestacion.ts:35-38`) también dispararía logout. No se agregó
  distinción adicional por motivo del error.
