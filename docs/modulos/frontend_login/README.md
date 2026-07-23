# Módulo Login — `frontend/src/features/auth/` + rutas asociadas

Primer módulo de **frontend** documentado en `docs/modulos/` (los 19 anteriores — 17 en
`services/presupuestacion/` y 2 en `services/extraccion/` — son de backend). La estructura de
contenido difiere de esos módulos donde corresponde: este módulo no es dueño de ninguna tabla de
Supabase, así que no tiene `base_de_datos.md`; tampoco tiene una máquina de estados propia digna
de un `estados.md` (ver `arquitectura.md`).

## Qué es

Login resuelve la autenticación del frontend nuevo (Vite + React + TanStack Router +
`supabase-js`): formulario de email/contraseña, sesión persistida vía Supabase Auth, resolución de
rol de negocio contra `services/presupuestacion`, guard de rutas que redirige a `/login` cuando no
hay sesión o cuando el rol no alcanza, y los flujos de recuperación de contraseña e
invitación/activación de cuenta (ambos basados en el mismo mecanismo de sesión temporal desde un
link de Supabase Auth). Ya no es un módulo mínimo: 12 archivos fuente en el alcance de esta
documentación, 592 líneas en total (`AuthContext.tsx` 126, `MiCuenta.tsx` — ver nota de alcance
abajo, no cuenta acá —, `reset-password.tsx` 97, `SetPasswordForm.tsx` 86, `LoginForm.tsx` 73,
`_authenticated.tsx` 34, `login.tsx` 32, `useSessionFromLink.ts` 30, `accept-invite.tsx` 29,
`routeGuards.ts` 22, `supabase.ts` 14, `__root.tsx` 10, más el fragmento de bootstrap en
`main.tsx` 39 — verificado leyendo cada archivo completo en esta sesión).

**"Mi cuenta"** (`features/mi-cuenta/MiCuenta.tsx` + `routes/_authenticated.mi-cuenta.tsx`) se
documenta aparte, en [`../frontend_mi_cuenta/`](../frontend_mi_cuenta/README.md): reusa
`AuthContext` (`perfil`, `session`, `signOut`, `refrescarPerfil`) y `lib/supabase.ts`, pero es una
pantalla de gestión de datos propios, no de autenticación — separarla evita que este módulo mezcle
"cómo entro a la app" con "cómo edito mi perfil ya adentro".

Documentado retroactivamente: el código ya estaba implementado y verificado antes de escribir esta
documentación, igual que ocurrió con el proposal de origen —
[`openspec/changes/archive/login-frontend/proposal.md`](../../../openspec/changes/archive/login-frontend/proposal.md).
`frontend/PROGRESS.md:9` marca esta pantalla como "✅ Hecho", consistente con el estado real del
código verificado en esta sesión.

## Qué NO hace

- **No implementa registro de usuarios (alta libre).** [IMPLEMENTADO] el hecho: no se encontró
  ninguna llamada a `supabase.auth.signUp` en `frontend/src/` (confirmado por grep en esta sesión).
  El alta de un usuario nuevo la hace un admin/superadmin desde `usuarios/` (`invitarUsuario`,
  `lib/api/usuarios.ts:41-47`) y el usuario invitado activa su cuenta vía `/accept-invite` — ver
  más abajo. No hay autoservicio de "crear cuenta" sin invitación previa.
- **Recuperación de contraseña SÍ está implementada — corrige el estado documentado
  anteriormente.** `D-LOGIN-004` (que declaraba esto fuera de scope) quedó superada por
  `/reset-password`: pide el email, llama a `supabase.auth.resetPasswordForEmail`, y el link del
  mail deja al navegador con una sesión temporal que habilita `SetPasswordForm`. Ver
  [`decisiones.md`](./decisiones.md) D-LOGIN-004 (marcada como superada) y
  [`flujo.md`](./flujo.md).
- **`requireRole(...)` SÍ tiene call sites — corrige el estado documentado anteriormente.**
  `routeGuards.ts:15-22` define la función; a diferencia de lo registrado antes (cuando el proposal
  original la dejó "armada pero sin ningún call site"), un grep de `requireRole` en esta sesión
  encuentra **dos usos reales**: `routes/_authenticated.admin.usuarios.tsx:6`
  (`requireRole('admin', 'superadmin')`) y `routes/_authenticated.superadmin.empresas.tsx:6`
  (`requireRole('superadmin')`). Ambos archivos están fuera del alcance de esta documentación (no
  son parte del módulo Login), pero se cita el hecho acá porque invalida la afirmación anterior y
  porque es la causa raíz del bug de timing corregido en esta sesión — ver
  [`decisiones.md`](./decisiones.md) D-LOGIN-005.
- **No tiene `estados.md`.** El único estado de sesión real (`session: Session | null` en
  `AuthContext.tsx:19`) es binario y no tiene transiciones intermedias documentables como máquina
  de estados — se cubre como parte de [`flujo.md`](./flujo.md) en su lugar. Mismo criterio aplicado
  en los módulos de backend Core y Usuarios cuando no hay una máquina de estados real.
- **No tiene `base_de_datos.md`.** El módulo no es dueño de ninguna tabla de Supabase: usa
  `supabase-js` exclusivamente para autenticación (`lib/supabase.ts:10-13`) y resuelve el perfil de
  negocio vía HTTP contra un backend ya documentado — ver la tabla de dependencias más abajo.
- **No hay tests de frontend en todo el repositorio.** Confirmado en esta sesión: `find` sobre
  `frontend/src` no encuentra ningún archivo `*.test.ts(x)` ni `*.spec.ts(x)`, y no hay
  configuración de `vitest` (sin `vitest.config.*` en `frontend/`, sin script `test` en
  `package.json`). Esto no es específico de Login — es una ausencia total del proyecto — pero se
  documenta acá como hallazgo porque es el primer módulo de frontend auditado. Ver
  [`pendientes.md`](./pendientes.md) P1(1).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `frontend/src/lib/supabase.ts` | Cliente `supabase-js` único del frontend, de uso exclusivo para login/logout/lectura de sesión. |
| `frontend/src/features/auth/AuthContext.tsx` | `AuthProvider` + hook `useAuth()`: estado de sesión, resolución secuenciada de `perfil`/rol (`loading` → `perfilLoading`), `signIn`/`signOut`/`refrescarPerfil`, logout automático si el fetch de perfil falla con 401/404. |
| `frontend/src/features/auth/LoginForm.tsx` | Componente de formulario email/contraseña, sin lógica de red propia (delega en `useAuth().signIn`); enlaza a `/reset-password`. |
| `frontend/src/features/auth/routeGuards.ts` | `requireAuth` y `requireRole` para `beforeLoad` de TanStack Router — **ambos usados** (ver corrección en "Qué NO hace"). |
| `frontend/src/features/auth/SetPasswordForm.tsx` | Formulario "definir contraseña" (`updateUser({password})` + `signOut` + vuelta a `/login`), reusado por `/reset-password` y `/accept-invite`. |
| `frontend/src/features/auth/useSessionFromLink.ts` | Hook que espera la sesión temporal que `supabase-js` deja tras procesar el link de recuperación/invitación, antes de mostrar `SetPasswordForm`. |
| `frontend/src/routes/login.tsx` | Ruta `/login`: renderiza `LoginForm`, redirige si ya hay sesión. |
| `frontend/src/routes/reset-password.tsx` | Ruta `/reset-password`: pide email (`resetPasswordForEmail`) o muestra `SetPasswordForm` si el link ya dejó sesión temporal. |
| `frontend/src/routes/accept-invite.tsx` | Ruta `/accept-invite`: mismo mecanismo que reset-password, para activar una cuenta invitada. |
| `frontend/src/routes/_authenticated.tsx` | Layout pathless: `beforeLoad: requireAuth` + `useEffect` reactivo que redirige a `/login` si `isAuthenticated` pasa a `false` con la pantalla ya montada; monta el `Sidebar`. |
| `frontend/src/routes/__root.tsx` | Raíz del router; define el `RouterContext` tipado con `auth` (contexto, no lógica de auth en sí). |
| `frontend/src/main.tsx` (fragmento `InnerApp`) | Bootstrap del router: espera `auth.loading || auth.perfilLoading` antes de montar `RouterProvider`. Fuera del árbol de `features/auth/` pero documentado acá porque es la mitad de la corrección del bug de timing — ver [`decisiones.md`](./decisiones.md) D-LOGIN-005. |

## Dependencias

- **Supabase Auth (directo, vía `supabase-js`)** — único uso permitido del cliente de
  `lib/supabase.ts`: `signInWithPassword`, `signOut`, `getSession`, `onAuthStateChange`,
  `resetPasswordForEmail`, `updateUser({password})` (`AuthContext.tsx`, `SetPasswordForm.tsx`,
  `reset-password.tsx`, `useSessionFromLink.ts`). Ningún dato de negocio se lee con este cliente
  (`lib/supabase.ts:10-13`).
- **`services/presupuestacion` — módulo Usuarios** (ya documentado en
  [`../usuarios/`](../usuarios/)) — `AuthContext.tsx` hace `GET /usuarios/{id}` para resolver el
  perfil/rol del usuario autenticado (`AuthContext.tsx:73`). Ver el contrato exacto del endpoint en
  [`../usuarios/api.md`](../usuarios/api.md) (fila `GET /usuarios/{usuario_id}`).
- **`frontend/src/lib/api/presupuestacion.ts`** — el wrapper `presupuestacionFetch`/`ApiError` que
  usa `AuthContext.tsx:73` para llamar al backend, y cuyo `ApiError.status` (`presupuestacion.ts:5-13`,
  `:37`) es lo que `AuthContext.tsx:82` inspecciona para decidir el `signOut` automático. También es
  el encargado de inyectar `Authorization: Bearer <token>` en toda llamada a
  `services/presupuestacion` (`lib/api/presupuestacion.ts:19-31`). No es parte del alcance de
  archivos de esta documentación, pero se cita porque de ahí viene la señal 401/404 — ver
  [`arquitectura.md`](./arquitectura.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — relación entre `AuthContext`/`LoginForm`/`routeGuards`/
  `supabase.ts`, dónde vive el JWT y cómo se inyecta en llamadas al backend.
- [`reglas.md`](./reglas.md) — reglas reales del módulo (RN-LOGIN-NNN).
- [`flujo.md`](./flujo.md) — flujo de login, logout y guard de ruta no autenticada, paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — rutas cubiertas, endpoint de backend consumido, roles.
- [`api.md`](./api.md) — funciones/componentes/hooks públicos de cada archivo, con firma.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-LOGIN-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría P1/P2/P3.
