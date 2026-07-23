# Arquitectura — Login

## Piezas y relación entre ellas

```
                        supabase.ts
                  (cliente supabase-js único)
                             │
        ┌────────────────────┼─────────────────────────┐
        │                    │                          │
 AuthContext.tsx      useSessionFromLink.ts       SetPasswordForm.tsx
(AuthProvider+useAuth)  (getSession +              (updateUser+signOut,
        │               onAuthStateChange)          sin conocer AuthContext)
        │                    │                          │
        │           ┌────────┴────────┐         reusado por ambas rutas
        │           │                 │                  │
        │    routes/reset-password.tsx  routes/accept-invite.tsx
        │
   ┌────┼───────────────────────┬──────────────────┐
   │    │                       │                   │
LoginForm.tsx  routeGuards.ts   routes/login.tsx   routes/_authenticated.tsx
(usa signIn,   (usa isAuthenticated/perfil          (beforeLoad: requireAuth +
 enlaza a       vía context del router;              useEffect reactivo sobre
 /reset-password) 2 call sites reales fuera           isAuthenticated)
                   del alcance — ver abajo)
```

- **`supabase.ts`** (`frontend/src/lib/supabase.ts:1-14`) crea el único cliente `supabase-js` del
  frontend con `createClient(SUPABASE_URL, SUPABASE_ANON_KEY)` (`supabase.ts:14`), leyendo
  `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` de `import.meta.env` (`supabase.ts:3-4`) y lanzando
  si faltan (`supabase.ts:6-8`). El comentario del archivo (`supabase.ts:10-13`) documenta la
  restricción de uso: "Uso exclusivo: login/logout y lectura de la sesión (JWT)... Ningún dato de
  negocio se consulta con este cliente". Sin cambios de código en esta sesión.
- **`AuthContext.tsx`** es el consumidor principal de `supabase` dentro del alcance de esta
  documentación (`AuthContext.tsx:4`). Expone `AuthProvider` (componente) y `useAuth()` (hook) —
  ver firmas exactas en [`api.md`](./api.md). Ahora resuelve `perfil` en un segundo paso
  explícitamente secuenciado después de `session`/`loading` (`perfilLoading`, `:41`, `:58-87`) y
  hace `signOut()` automático si ese segundo paso falla con 401/404 (`:75-84`) — ver la sección de
  bugs corregidos, más abajo.
- **`useSessionFromLink.ts`** también consume `supabase` directamente (`getSession` +
  `onAuthStateChange`, `useSessionFromLink.ts:14-24`), en paralelo a `AuthContext.tsx` — es un hook
  independiente, no delega en `useAuth()`. Sirve exclusivamente a `routes/reset-password.tsx` y
  `routes/accept-invite.tsx`.
- **`SetPasswordForm.tsx`** también consume `supabase` directamente (`updateUser`/`signOut`,
  `SetPasswordForm.tsx:29-32`); tampoco depende de `AuthContext.tsx`. Es un componente puro
  reusado sin cambios entre las dos rutas que lo montan.
- **`LoginForm.tsx`** no importa `supabase.ts` ni `lib/api/*` directamente: solo consume
  `useAuth().signIn` (`LoginForm.tsx:6`, `:17`). No tiene lógica de red propia. Agrega un `<Link
  to="/reset-password">` (`LoginForm.tsx:68-70`).
- **`routeGuards.ts`** no importa `AuthContext.tsx` ni `supabase.ts`: recibe el estado de auth como
  parámetro (`context.auth`, tipado en `GuardArgs`, `routeGuards.ts:4-7`) inyectado por TanStack
  Router — ver más abajo cómo llega ese contexto. **Corrección frente a la versión anterior de esta
  documentación**: `requireRole` ya no es código sin uso — tiene 2 call sites reales,
  `routes/_authenticated.admin.usuarios.tsx:6` y `routes/_authenticated.superadmin.empresas.tsx:6`
  (ambos fuera del alcance de archivos de esta documentación). Eso es justamente lo que hace
  observable el bug de timing corregido en esta sesión (ver más abajo): `requireRole` lee
  `context.auth.perfil`, que antes podía llegar `null` al montar el router.
- **`routes/login.tsx`**, **`routes/reset-password.tsx`**, **`routes/accept-invite.tsx`** y
  **`routes/_authenticated.tsx`** son los puntos de entrada de UI/routing: el primero renderiza
  `LoginForm`; los dos siguientes resuelven, vía `useSessionFromLink`, si mostrar el formulario de
  pedido de link o `SetPasswordForm`; el último aplica el guard a todo lo que cuelga de él y ahora
  además redirige reactivamente si la sesión se cae estando ya montado.

## Dónde vive el JWT y cómo llega al contexto del router

El JWT no se guarda a mano: `supabase-js` persiste la sesión (`Session`, que incluye
`access_token`) según su comportamiento por defecto de cliente — no hay ningún código en el
alcance de esta documentación que lea o escriba `localStorage` explícitamente; `AuthContext.tsx`
solo llama a `supabase.auth.getSession()` (`AuthContext.tsx:44-47`) y se suscribe a
`supabase.auth.onAuthStateChange()` (`AuthContext.tsx:49-53`) para mantener `session` actualizado
en el estado de React.

El contexto tipado de TanStack Router (`RouterContext`, `__root.tsx:4-6`) declara `auth:
ReturnType<typeof useAuth>` pero **no lo llena** — `__root.tsx` solo define el tipo y renderiza
`<Outlet />` (`__root.tsx:8-10`). El valor real se inyecta fuera del alcance de archivos de esta
documentación, en `frontend/src/main.tsx`: `InnerApp()` llama a `useAuth()` (`main.tsx:23`), bloquea
el render mientras `auth.loading || auth.perfilLoading` es `true` (`main.tsx:27`), y pasa ese valor
como `context={{ auth }}` a `<RouterProvider>` (`main.tsx:28`). Ese es el mecanismo por el cual
`routeGuards.ts` recibe `context.auth` sin importar `AuthContext.tsx` directamente.

## Bug de timing corregido: `main.tsx` esperaba solo `loading`, no `perfilLoading`

Antes de esta sesión, `InnerApp()` solo esperaba `auth.loading` (resolución de la sesión de
Supabase) antes de montar el `RouterProvider`. Pero `perfil` se resuelve en un segundo paso
asíncrono aparte (el fetch a `GET /usuarios/{id}` dentro de `AuthContext.tsx`), y `requireRole()`
(`routeGuards.ts:15-22`) depende de `context.auth.perfil` para decidir si autoriza. El router podía
montarse — y `beforeLoad` podía correr — con `session` ya resuelta pero `perfil` todavía `null`.

**Síntoma reproducido en esta sesión** (confirmado en vivo con Chrome): recargar directamente (deep
link) una ruta con `requireRole`, como `/admin/usuarios`, rebotaba a `/` aunque el usuario
autenticado tuviera el rol correcto — porque `requireRole` veía `perfil: null` en ese instante y
tomaba la rama de "no autorizado" (`routeGuards.ts:18-20`).

**Fix**: `AuthContext.tsx` expone ahora `perfilLoading` (`AuthContext.tsx:23`, `:41`), secuenciado
explícitamente para no arrancar hasta que `loading` sea `false` (guard en `:62`, comentario
`:58-61`); `main.tsx` espera `auth.loading || auth.perfilLoading` antes de montar el router
(`main.tsx:26-27`). Ver [`decisiones.md`](./decisiones.md) D-LOGIN-005.

## Bug corregido: perfil inaccesible (401/404) con sesión de Supabase viva → "Cargando…" infinito

Si el fetch de `perfil` fallaba con 401 (usuario desactivado — ver
`services/presupuestacion/core/auth.py` `get_current_user`, RN-CORE-026 en `../core/reglas.md`) o
404 (fila de usuario borrada) mientras la sesión de Supabase seguía técnicamente viva, no había
ningún manejo explícito: `perfil` quedaba en `null` para siempre y `isAuthenticated` seguía en
`true`, así que la UI (por ejemplo el `Sidebar`) quedaba mostrando un estado de carga indefinido,
sin logout ni redirección — **reproducido en vivo en esta sesión**.

**Fix, en dos partes**:

1. `AuthContext.tsx` inspecciona el `catch` de la resolución de `perfil`: si el error es una
   `ApiError` (`lib/api/presupuestacion.ts:5-13`) con `status` 401 o 404, llama a
   `supabase.auth.signOut()` automáticamente (`AuthContext.tsx:75-84`).
2. `routes/_authenticated.tsx` (`AuthenticatedLayout`) agrega un `useEffect` reactivo
   (`_authenticated.tsx:16-24`) que redirige a `/login` si `isAuthenticated` pasa a `false`
   **mientras el usuario ya está montado** en una pantalla protegida — antes, el guard
   `requireAuth` solo corría una vez, al entrar a la ruta, vía `beforeLoad`, y no reaccionaba a que
   la sesión se cayera después.

Ver [`decisiones.md`](./decisiones.md) D-LOGIN-006.

## Mecanismo de sesión temporal desde un link (reset de contraseña e invitación)

`routes/reset-password.tsx` y `routes/accept-invite.tsx` comparten el mismo mecanismo: cuando
Supabase Auth envía un mail de recuperación o de invitación, el link apunta de vuelta al frontend
con un fragmento de URL que `supabase-js` procesa automáticamente al cargar la página
(`detectSessionInUrl`, comportamiento por defecto del SDK — no hay parsing manual del fragmento en
el alcance de esta documentación), dejando al navegador con una **sesión temporal**.
`useSessionFromLink()` espera esa sesión (`useSessionFromLink.ts:9-30`) antes de decidir qué
mostrar:

- **`hasSession: true`** → se monta `SetPasswordForm`, que pide la contraseña nueva,
  `supabase.auth.updateUser({ password })`, luego `signOut()` y navega a `/login`
  (`SetPasswordForm.tsx:29-32`) — el usuario tiene que loguearse de nuevo con la contraseña recién
  puesta, no queda logueado automáticamente.
- **`hasSession: false`** → cada ruta muestra su propio estado alternativo: `/reset-password`
  muestra el formulario para pedir un nuevo link (`SolicitarResetForm`, `reset-password.tsx:30-97`);
  `/accept-invite` muestra un mensaje fijo de "link inválido o expirado", sin ninguna acción de
  reenvío propia (`accept-invite.tsx:21-24`).

La única diferencia real entre ambas pantallas es el `title`/`submitLabel` pasado a
`SetPasswordForm` y el mensaje mostrado cuando no hay sesión — toda la lógica de red vive en el
hook y el componente compartidos.

## Cómo se inyecta el JWT en llamadas al backend

Este módulo (`AuthContext.tsx`, `LoginForm.tsx`, `routeGuards.ts`, rutas) **no inyecta el JWT en
llamadas HTTP él mismo** — esa responsabilidad es de `frontend/src/lib/api/presupuestacion.ts`
(fuera del alcance de archivos de esta documentación, pero citado porque `AuthContext.tsx` lo
consume directamente):

```
presupuestacionFetch<T>(path, init) // lib/api/presupuestacion.ts:19-41
  → supabase.auth.getSession()                    // :20-22, mismo cliente de supabase.ts
  → header Authorization: Bearer <session.access_token>   // :28, solo si hay sesión
```

`AuthContext.tsx:73` llama a `presupuestacionFetch<Perfil>('/usuarios/${session.user.id}')` para
resolver el perfil/rol — esa es la única llamada a `services/presupuestacion` que hace el módulo
Login en sí (`refrescarPerfil()`, `AuthContext.tsx:89-93`, llama al mismo endpoint bajo demanda).
Cualquier otro módulo de frontend que use `presupuestacionFetch` hereda automáticamente la misma
inyección de JWT, sin código adicional de su parte.

## Por qué no hay `estados.md`

El único estado de sesión relevante es `session: Session | null` (`AuthContext.tsx:19`, `:32`),
con dos valores posibles y sin estados intermedios (no hay "verificando", "expirado", etc. como
valores explícitos — ver [`pendientes.md`](./pendientes.md) sobre expiración/refresh). El flujo de
transición entre esos dos valores se documenta como parte de [`flujo.md`](./flujo.md); no se
consideró que amerite un diagrama de estados dedicado. (`perfilLoading` es binario por la misma
razón — no se le agregó un diagrama de estados propio.)

## Dependencia hacia `services/presupuestacion` — módulo Usuarios

Ver tabla de dependencias en [`README.md`](./README.md). El contrato completo de
`GET /usuarios/{usuario_id}` (parámetros, respuesta `UsuarioOut`, autorización) está documentado en
[`../usuarios/api.md`](../usuarios/api.md) — no se repite acá. Desde el lado de Login, el campo
relevante de la respuesta es `rol: Rol` (`AuthContext.tsx:6-16` — nota: `Rol` se redeclara en
`AuthContext.tsx:6` con la misma lista de 6 valores que `usuarios/models.py:5` del backend, sin
compartir el tipo entre ambos proyectos — ver [`decisiones.md`](./decisiones.md)).
