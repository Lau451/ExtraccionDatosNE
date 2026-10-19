# Módulo Mi cuenta — `frontend/src/features/mi-cuenta/` + `routes/_authenticated.mi-cuenta.tsx`

Módulo liviano de **frontend**, documentado en un único archivo (a diferencia de
[`../frontend_login/`](../frontend_login/README.md), que usa la estructura completa de 8 archivos).
Criterio: 2 archivos fuente, 120 líneas en total (`MiCuenta.tsx` 114, `_authenticated.mi-cuenta.tsx`
6), sin reglas de negocio propias (delega todo en endpoints del backend), sin flujo con
ramificaciones complejas.

## Qué es

Pantalla de autogestión de la cuenta del usuario ya autenticado: ver su nombre de usuario, editar
nombre/apellido, ir a cambiar la contraseña y cerrar sesión. Accesible desde `Sidebar.tsx:94`
(`<Link to="/mi-cuenta">`, fuera del alcance de esta documentación) y montada bajo el layout
`/_authenticated` (ver [`../frontend_login/`](../frontend_login/README.md) para el guard de sesión
y el de cambio de contraseña pendiente).

## Qué NO hace

- **No permite cambiar el email.** El formulario "Cambiar email" (`supabase.auth.updateUser({ email })`)
  se eliminó con el login por nombre de usuario (odd/tasks/login-usuario-alta-admin.md, S1/L-T4a):
  el email de Supabase Auth es interno, nunca se muestra ni se edita desde el frontend
  (comentario en `MiCuenta.tsx:27-28`).
- **No cambia la contraseña con `supabase-js`.** El formulario propio que usaba
  `supabase.auth.updateUser({ password })` se reemplazó por un link a `/cambiar-password`
  (`MiCuenta.tsx:29-37`), la misma pantalla del cambio forzado, que llama a
  `POST /auth/cambiar-password` (ver `../frontend_login/`).
- **No permite editar el nombre de usuario, el rol ni la droguería propios.** El username se
  muestra solo como texto (`MiCuenta.tsx:21-23`); lo edita un admin desde gestión de usuarios
  (`PATCH /usuarios/{id}/username`). Solo `nombre`/`apellido` son editables
  (`ActualizarPerfilPayload`, `lib/api/usuarios.ts:18-21`).

## Componentes y qué hacen

| Pieza | Archivo | Qué hace |
|---|---|---|
| `MiCuenta` (componente de página) | `features/mi-cuenta/MiCuenta.tsx:6-50` | Lee `perfil`/`signOut` de `useAuth()`; si `perfil` es `null` no renderiza nada (`:15`). Muestra `perfil.username` (`:21-23`), `EditarNombreForm`, la sección "Contraseña" y el botón de logout. |
| `EditarNombreForm` | `MiCuenta.tsx:52-114` | Formulario controlado de `nombre`/`apellido`, prellenado desde `perfil` (`:25`, con `apellido ?? ''`). `PATCH /usuarios/me` vía `actualizarPerfilPropio` (`lib/api/usuarios.ts:34-40`) y luego `refrescarPerfil()` (`MiCuenta.tsx:65-66`). |
| Link "Cambiar contraseña" | `MiCuenta.tsx:29-37` | `<Link to="/cambiar-password">`. En esa pantalla, sin cambio forzado, se muestra "Cancelar" que vuelve a `/mi-cuenta` (`features/auth/CambiarPasswordPage.tsx:34-41`). |
| Botón "Cerrar sesión" | `MiCuenta.tsx:39-47`, `handleLogout` en `:10-13` | `await signOut()` seguido de `navigate({ to: '/login' })`. |
| Ruta `/mi-cuenta` | `routes/_authenticated.mi-cuenta.tsx:1-6` | Sin `beforeLoad` propio; hereda `requireAuth` del layout `_authenticated.tsx` (que además manda a `/cambiar-password` si hay cambio pendiente). No usa `requireRole`: es el destino de `homeForRol` cuando no hay perfil resuelto (`features/auth/routeGuards.ts:31-36`). |

[IMPLEMENTADO] todo lo anterior. Cubierto por `features/mi-cuenta/MiCuenta.test.tsx`.

## Dependencias

- **`../frontend_login/`** — `useAuth()` (`perfil`, `signOut`, `refrescarPerfil`), los guards y la
  ruta `/cambiar-password`.
- **`services/presupuestacion` — módulo Usuarios** — `PATCH /usuarios/me` vía
  `actualizarPerfilPropio`. Contrato en [`../usuarios/api.md`](../usuarios/api.md).
- Ya no usa `supabase-js` directamente.

## Reglas verificadas

- **Solo `nombre`/`apellido` son editables desde esta pantalla** — `ActualizarPerfilPayload`
  acota los campos; el backend actualiza solo los provistos (RN-USUARIOS-028 en
  `../usuarios/reglas.md`). [IMPLEMENTADO].
- **`refrescarPerfil()` es la vía por la que esta pantalla actualiza el estado global de
  `perfil`** tras editar el nombre. [IMPLEMENTADO].

## Pendientes

- **P3**: sin loading state propio si `perfil` es `null` (`MiCuenta.tsx:15` retorna `null`) —
  depende de que `main.tsx` ya haya esperado `perfilLoading` (ver `../frontend_login/`).
