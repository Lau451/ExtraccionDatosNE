# Casos de uso — Login

## Rutas cubiertas

| Ruta | Archivo | Protegida | Qué hace |
|---|---|---|---|
| `/login` | `frontend/src/routes/login.tsx` | No (pública) | Formulario de email/contraseña; redirige si ya hay sesión. |
| `/reset-password` | `frontend/src/routes/reset-password.tsx` | No (pública) | Pide email para recuperar contraseña, o muestra `SetPasswordForm` si el link ya dejó sesión temporal. |
| `/accept-invite` | `frontend/src/routes/accept-invite.tsx` | No (pública) | Activa una cuenta invitada vía sesión temporal + `SetPasswordForm`. |
| `/_authenticated` (layout pathless) | `frontend/src/routes/_authenticated.tsx` | Sí, vía `beforeLoad: requireAuth` (`_authenticated.tsx:8`) + `useEffect` reactivo (`:16-24`) | Agrupa todas las rutas que requieren sesión; monta `Sidebar` + `<Outlet />`. Las rutas hijas concretas (incluidas las que agregan `requireRole`, ver "Roles" abajo) están fuera del alcance de esta documentación. |

`__root.tsx` no define una ruta navegable en sí, solo el nodo raíz y el tipo de contexto. Otra
ruta relacionada, `/_authenticated/mi-cuenta`, está documentada en
[`../frontend_mi_cuenta/`](../frontend_mi_cuenta/README.md) (no en este módulo).

## Endpoint de backend consumido

| Método | Path | Backend | Quién lo llama | Evidencia |
|---|---|---|---|---|
| GET | `/usuarios/{usuario_id}` | `services/presupuestacion` | `AuthContext.tsx` (useEffect de resolución de perfil, y `refrescarPerfil()`) | `AuthContext.tsx:73`: `presupuestacionFetch<Perfil>(`/usuarios/${session.user.id}`)`; `AuthContext.tsx:91` (misma llamada en `refrescarPerfil`) |

Contrato completo (request/response/roles requeridos) documentado en
[`../usuarios/api.md`](../usuarios/api.md), fila `GET /usuarios/{usuario_id}` — según esa
documentación, ese endpoint solo exige `Depends(get_current_user)` (cualquier usuario autenticado,
sin rol específico), consistente con que Login lo llame apenas resuelta la sesión, antes de conocer
el rol del usuario. Notar que `get_current_user` ahora rechaza con 401 si el usuario está
desactivado (`core/auth.py`, RN-CORE-026 en `../core/reglas.md`) — ese 401 es justamente lo que
dispara el `signOut()` automático de `AuthContext.tsx:83` (ver [`decisiones.md`](./decisiones.md)
D-LOGIN-006).

Además, indirectamente, toda llamada a Supabase Auth (`signInWithPassword`, `getSession`,
`signOut`, `onAuthStateChange`, `resetPasswordForEmail`, `updateUser`) es una interacción con el
servicio de Supabase Auth del proyecto — no un endpoint propio de `services/presupuestacion` ni
`services/extraccion`. Ver [`arquitectura.md`](./arquitectura.md) para el detalle de qué cliente se
usa y con qué restricciones.

## Roles

El login en sí **no distingue roles**: cualquier usuario con credenciales válidas en Supabase Auth
puede autenticarse y llegar a `isAuthenticated: true`, independientemente de su `rol` resuelto
(`perfil.rol`). La guard usada por `/_authenticated` en sí, `requireAuth` (`routeGuards.ts:9-13`),
no consulta `perfil` en ningún punto.

`requireRole(...roles: Rol[])` (`routeGuards.ts:15-22`) restringe por rol, aceptando cualquier
combinación de los 6 valores de `Rol` (`superadmin`, `admin`, `gerencia`, `lider_comercial`,
`comercial`, `compras` — `AuthContext.tsx:6`, idéntica a la lista del backend en
`usuarios/models.py:5`). **Corrección frente a la versión anterior de esta documentación**: sí
tiene call sites reales, ambos fuera del alcance de archivos de este módulo:

| Ruta | `requireRole(...)` | Archivo |
|---|---|---|
| `/_authenticated/admin/usuarios` | `'admin'`, `'superadmin'` | `routes/_authenticated.admin.usuarios.tsx:6` |
| `/_authenticated/superadmin/empresas` | `'superadmin'` | `routes/_authenticated.superadmin.empresas.tsx:6` |

Ver [`README.md`](./README.md), [`decisiones.md`](./decisiones.md) (D-LOGIN-003 corregida,
D-LOGIN-005) y [`pendientes.md`](./pendientes.md).
