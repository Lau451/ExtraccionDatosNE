# Módulo Login — `frontend/src/features/auth/` + rutas asociadas

Primer módulo de **frontend** documentado en `docs/modulos/`. Este módulo no es dueño de ninguna
tabla de Supabase, así que no tiene `base_de_datos.md`; tampoco tiene una máquina de estados
propia digna de un `estados.md` (ver `arquitectura.md`).

## Qué es

Login resuelve la autenticación del frontend (Vite + React + TanStack Router + `supabase-js`):
formulario de **nombre de usuario** y contraseña que se valida en el backend
(`POST /auth/login`), sesión de Supabase instalada con `setSession` y persistida por
`supabase-js`, resolución de rol de negocio contra `services/presupuestacion`, guards de ruta que
redirigen a `/login` sin sesión, a `/cambiar-password` mientras la contraseña sea temporal, o a la
home del rol cuando el rol no alcanza, y la pantalla de cambio de contraseña (forzado o
voluntario).

**Cambio de odd/tasks/login-usuario-alta-admin.md**: se reemplazó el login por email
(`signInWithPassword` desde el navegador) por el login con username vía backend, y se eliminaron
la recuperación de contraseña por email (`/reset-password`) y la activación de cuenta invitada
(`/accept-invite`), junto con `SetPasswordForm.tsx` y `useSessionFromLink.ts`. Si alguien olvida
la contraseña, el login le indica contactar al administrador, que se la blanquea.

Archivos fuente en el alcance (`wc -l`): `AuthContext.tsx` 162, `CambiarPasswordForm.tsx` 112,
`LoginForm.tsx` 81, `CambiarPasswordPage.tsx` 52, `routeGuards.ts` 46, `lib/api/auth.ts` 45,
`login.tsx` 44, `_authenticated.tsx` 39, `cambiar-password.tsx` 15, `supabase.ts`, `__root.tsx`, y
el fragmento de bootstrap de `main.tsx`.

**"Mi cuenta"** se documenta aparte, en [`../frontend_mi_cuenta/`](../frontend_mi_cuenta/README.md):
reusa `AuthContext` y enlaza a `/cambiar-password`, pero es una pantalla de gestión de datos
propios, no de autenticación.

## Qué NO hace

- **No implementa registro de usuarios (alta libre).** No hay `supabase.auth.signUp` en
  `frontend/src/`. El alta la hace un admin desde gestión de usuarios (`crearUsuario`,
  `lib/api/usuarios.ts:46-52`) con username + contraseña temporal; ver
  [`../usuarios/`](../usuarios/README.md).
- **No hay recuperación de contraseña por email.** Se eliminó `/reset-password`
  (D-LOGIN-008). El login muestra "¿Olvidaste tu contraseña? Contactá al administrador para que te
  la blanquee." (`LoginForm.tsx:76-78`).
- **No muestra ni conoce el email de Supabase Auth.** El backend resuelve username → email interno
  y devuelve solo la sesión (`lib/api/auth.ts:1-20`).
- **No tiene `estados.md` ni `base_de_datos.md`.** Ver [`arquitectura.md`](./arquitectura.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `frontend/src/lib/supabase.ts` | Cliente `supabase-js` único del frontend: sesión (`setSession`, `getSession`, `onAuthStateChange`, refresh) y logout. Ya no hace el sign-in. |
| `frontend/src/lib/api/auth.ts` | `iniciarSesion` (`POST /auth/login`, `fetch` directo sin `Authorization`) y `cambiarPasswordPropia` (`POST /auth/cambiar-password`). |
| `frontend/src/features/auth/AuthContext.tsx` | `AuthProvider` + `useAuth()`: sesión, resolución secuenciada de `perfil` (con `username` y `debe_cambiar_password`), `signIn(username, password)`/`signOut`/`refrescarPerfil`, logout automático si el perfil falla con 401/404. |
| `frontend/src/features/auth/LoginForm.tsx` | Formulario usuario/contraseña; mensaje de contactar al administrador. |
| `frontend/src/features/auth/routeGuards.ts` | `requireSession`, `requireAuth` (sesión + cambio pendiente), `requireRole`, `homeForRol`. |
| `frontend/src/features/auth/CambiarPasswordForm.tsx` | Formulario contraseña actual / nueva / repetir; llama a `POST /auth/cambiar-password` y refresca el perfil. |
| `frontend/src/features/auth/CambiarPasswordPage.tsx` | Pantalla fuera del layout con sidebar: texto de contraseña temporal si es forzado, "Cancelar" solo si es voluntario, "Cerrar sesión" siempre. |
| `frontend/src/routes/login.tsx` | Ruta `/login`: renderiza `LoginForm`, redirige si ya hay sesión. |
| `frontend/src/routes/cambiar-password.tsx` | Ruta `/cambiar-password` con `beforeLoad: requireSession`. |
| `frontend/src/routes/_authenticated.tsx` | Layout pathless: `beforeLoad: requireAuth` + `useEffect` reactivo que redirige a `/login` sin sesión o a `/cambiar-password` con cambio pendiente; monta el `Sidebar`. |
| `frontend/src/routes/__root.tsx` | Raíz del router; define el `RouterContext` tipado con `auth`. |
| `frontend/src/main.tsx` (fragmento `InnerApp`) | Espera `auth.loading \|\| auth.perfilLoading` antes de montar `RouterProvider` (D-LOGIN-005). |

## Dependencias

- **`services/presupuestacion` — `POST /auth/login` y `POST /auth/cambiar-password`** (paquete
  `services/presupuestacion/auth/`, documentado en [`../usuarios/`](../usuarios/README.md)).
- **`services/presupuestacion` — módulo Usuarios** — `GET /usuarios/{id}` para resolver el perfil
  (`AuthContext.tsx:75`); contrato en [`../usuarios/api.md`](../usuarios/api.md).
- **Supabase Auth (vía `supabase-js`)** — `setSession`, `getSession`, `onAuthStateChange`,
  `signOut` (`AuthContext.tsx:52-61`, `:126-129`, `:137`). Ningún dato de negocio se lee con este
  cliente.
- **`frontend/src/lib/api/presupuestacion.ts`** — `presupuestacionFetch`/`ApiError` y
  `PRESUPUESTACION_BASE_URL` (exportada para `lib/api/auth.ts`); inyecta
  `Authorization: Bearer <token>` en las llamadas autenticadas.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — piezas, dónde vive el JWT, cómo llega al router.
- [`reglas.md`](./reglas.md) — reglas reales del módulo (RN-LOGIN-NNN).
- [`flujo.md`](./flujo.md) — login, logout, guards y cambio de contraseña paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — rutas cubiertas, endpoints consumidos, roles.
- [`api.md`](./api.md) — funciones/componentes/hooks públicos de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-LOGIN-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría P1/P2/P3.
