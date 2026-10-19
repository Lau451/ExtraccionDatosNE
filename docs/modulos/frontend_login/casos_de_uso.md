# Casos de uso — Login

## Rutas cubiertas

| Ruta | Archivo | Protegida | Qué hace |
|---|---|---|---|
| `/login` | `frontend/src/routes/login.tsx` | No (pública) | Formulario de usuario/contraseña; redirige si ya hay sesión. |
| `/cambiar-password` | `frontend/src/routes/cambiar-password.tsx` | Sí, `beforeLoad: requireSession` (`cambiar-password.tsx:8`) — solo sesión, sin chequeo de cambio pendiente (evita el loop) | Cambio de la propia contraseña: forzado tras un alta o blanqueo, o voluntario desde Mi cuenta. Fuera del layout con sidebar. |
| `/_authenticated` (layout pathless) | `frontend/src/routes/_authenticated.tsx` | Sí, `beforeLoad: requireAuth` (`_authenticated.tsx:8`) + `useEffect` reactivo (`:17-29`) | Agrupa las rutas que requieren sesión; con cambio pendiente manda a `/cambiar-password`. |

**Eliminadas** (odd/tasks/login-usuario-alta-admin.md S4): `/reset-password` (recuperación por
email) y `/accept-invite` (activación de cuenta invitada). Ya no existen en
`frontend/src/routes/` ni en `routeTree.gen.ts`.

Otra ruta relacionada, `/_authenticated/mi-cuenta`, está documentada en
[`../frontend_mi_cuenta/`](../frontend_mi_cuenta/README.md).

## Endpoints de backend consumidos

| Método | Path | Quién lo llama | Evidencia |
|---|---|---|---|
| POST | `/auth/login` | `signIn` de `AuthContext` vía `iniciarSesion` | `lib/api/auth.ts:22-37`, `AuthContext.tsx:125` |
| POST | `/auth/cambiar-password` | `CambiarPasswordForm` vía `cambiarPasswordPropia` | `lib/api/auth.ts:39-45`, `CambiarPasswordForm.tsx:40` |
| GET | `/usuarios/{usuario_id}` | `cargarPerfil` de `AuthContext` (efecto de sesión, `signIn` y `refrescarPerfil`) | `AuthContext.tsx:75` |

Contratos completos en [`../usuarios/api.md`](../usuarios/api.md). `GET /usuarios/{id}` sobre el
propio id es uno de los dos endpoints permitidos con cambio de contraseña pendiente
(RN-USUARIOS-035), así que el perfil se resuelve aunque el resto de la API responda 403. Un 401
(usuario desactivado) o 404 de ese endpoint dispara el `signOut()` automático
(`AuthContext.tsx:84-86`, D-LOGIN-006).

Además, el frontend interactúa con Supabase Auth directamente solo para `setSession`,
`getSession`, `onAuthStateChange` y `signOut` — el sign-in ya no se hace desde el navegador.

## Roles

El login en sí **no distingue roles**. `requireAuth` (`routeGuards.ts:20-25`) exige sesión y que
`perfil.debe_cambiar_password` no sea `true`; no mira el rol.

`requireRole(...roles: Rol[])` (`routeGuards.ts:38-46`) restringe por rol sobre `requireAuth`:

| Ruta | `requireRole(...)` | Archivo |
|---|---|---|
| `/_authenticated/admin/usuarios` | `USUARIOS_ROLES` = `'admin'`, `'superadmin'`, `'gerencia'` | `routes/_authenticated.admin.usuarios.tsx:7` |
| `/_authenticated/superadmin/empresas` | `'superadmin'` | `routes/_authenticated.superadmin.empresas.tsx:6` |
| `/_authenticated/` (carga de documentos) | `CARGA_DOCUMENTOS_ROLES` | `routes/_authenticated.index.tsx:8` |

Desde la matriz de roles (odd/tasks/roles-permisos-matriz.md S9) todas las rutas de negocio
declaran `requireRole`. Un rol que no alcanza rebota a `homeForRol(rol)` (`routeGuards.ts:31-36`).

Ver [`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md).
