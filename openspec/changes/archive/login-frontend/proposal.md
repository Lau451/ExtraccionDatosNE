# Proposal: Login mínimo en frontend/

**Estado: archivado/completado.** Documentado retroactivamente el 2026-07-15 para adoptar la
convención de `openspec/` (ver `openspec/AGENTS.md`) — el código ya estaba implementado y
verificado antes de escribir este proposal.

**Actualización 2026-07-23**: el scope original ("login mínimo", explícitamente sin registro ni
recuperación de contraseña) quedó completado de verdad en esta sesión. Se reemplazó el alta por
password directa por invitación de email, y se agregaron recuperación de contraseña, aceptar
invitación y autoservicio de "Mi cuenta". Ver sección "Actualización 2026-07-23" abajo para el
detalle — no se reescribe el contenido original de este documento, que sigue siendo válido para el
scope que cubría.

## Intent

El frontend nuevo (Vite + React + TanStack Router) no tenía ningún mecanismo de autenticación:
todas las rutas eran públicas y `services/presupuestacion` exige JWT real en todos sus routers
(`require_roles`/`get_current_user`), por lo que ningún endpoint de ese backend era alcanzable
desde el frontend nuevo. Sin login no se podía avanzar con ninguna pantalla que dependiera de
`services/presupuestacion` (procesos comerciales, matching, presupuestos, etc.).

Se necesitaba el login mínimo indispensable: email/password, sesión persistida, JWT inyectado en
los pedidos a `services/presupuestacion`, y guard de rutas. Nada de registro ni recuperación de
contraseña — esas pantallas no están en el scope del MVP.

## Scope

### Incluido
- Cliente Supabase (`supabase-js`) de uso EXCLUSIVO para login/logout/lectura de sesión — nunca
  para consultar tablas de negocio directo (decisión explícita: todo dato de negocio pasa por los
  backends, que ya aplican RLS y lógica de dominio).
- Contexto de auth en React (sesión + perfil de usuario + rol).
- Guard de rutas: sin sesión, cualquier ruta protegida redirige a `/login?redirect=<ruta>`.
- Resolución de rol: el JWT de Supabase no trae `rol` como claim, así que se resuelve con un
  `GET /usuarios/{id}` contra `services/presupuestacion` (endpoint que ya existía).
- Fetch wrapper para `services/presupuestacion` que inyecta `Authorization: Bearer <token>` en
  cada llamada leyendo la sesión activa.

### Explícitamente fuera de scope
- Registro de usuarios nuevos.
- Recuperación/reset de contraseña.
- `requireRole(...)` con restricción granular por rol — se dejó la función armada pero sin ningún
  call site, porque ninguna ruta actual del MVP la necesita todavía.

## Approach

Patrón idiomático de TanStack Router para auth (confirmado contra la documentación vigente vía
context7, `/tanstack/router`): `createRootRouteWithContext<{ auth }>()` en `__root.tsx`, un layout
pathless `_authenticated.tsx` con `beforeLoad: requireAuth` que agrupa todas las rutas protegidas
(y donde vive el `Sidebar`), y `main.tsx` inyectando el contexto de auth al `RouterProvider` vía un
componente `InnerApp` que llama `useAuth()`.

Decisión explícita del usuario durante la implementación: cuando se evaluó resolver el rol con un
`SELECT` directo a la tabla `usuarios` desde supabase-js, se bloqueó esa opción y se pidió verificar
primero si ya existía un endpoint `/usuarios/{id}` o `/me` en el backend. Existía
(`services/presupuestacion/usuarios/router.py`, protegido solo con `get_current_user`) — se usó
tal cual, sin crear nada nuevo.

## Riesgos

Ninguno relevante para este scope acotado. El único riesgo real (rol resuelto vía llamada HTTP
extra en cada carga de sesión) es aceptado: es un solo GET, cacheable si hiciera falta más
adelante.

## Actualización 2026-07-23

### Intent

El scope original excluía explícitamente "registro de usuarios nuevos" y
"recuperación/reset de contraseña". Al construir las pantallas nuevas de gestión de usuarios y
gestión de empresas (fuera de las 8 pantallas del MVP, ver `openspec/changes/gestion-usuarios/` y
`openspec/changes/gestion-empresas/`) se necesitó una forma real de dar de alta usuarios sin que un
admin conociera ni definiera la contraseña de otra persona, y una forma de que un usuario recupere
el acceso si la olvida. Se resolvió ambas cosas con el mismo mecanismo de Supabase Auth
(invitación por email + link con sesión temporal), en vez de habilitar `signUp` libre.

### Scope incorporado

- `crear_usuario` (`services/presupuestacion/usuarios/service.py`) ya no acepta `password`; usa
  `client.auth.admin.invite_user_by_email` en vez de `client.auth.admin.create_user`. El body de
  `UsuarioCreate` suma `apellido` (obligatorio).
- `PATCH /usuarios/{id}/activo`, `PATCH /usuarios/me` y `DELETE /usuarios/{id}` — nuevos endpoints
  de `usuarios/`, con sus reglas de negocio (auto-modificación bloqueada, protección de
  `superadmin`/`sistema`, alcance por `drogueria_id` para `admin`). Detalle completo en
  `docs/modulos/usuarios/reglas.md` (RN-USUARIOS-013 en adelante).
- `frontend/src/routes/reset-password.tsx` — solicitar reset por email
  (`supabase.auth.resetPasswordForEmail`) y, si el link ya dejó una sesión temporal,
  `SetPasswordForm` para definir la nueva contraseña.
- `frontend/src/routes/accept-invite.tsx` — mismo mecanismo de sesión temporal
  (`useSessionFromLink`), reusado para activar una cuenta invitada.
- `frontend/src/routes/_authenticated.mi-cuenta.tsx` + `frontend/src/features/mi-cuenta/` —
  autoservicio de perfil: editar nombre/apellido (`PATCH /usuarios/me`), cambiar contraseña,
  cambiar email (verificación nativa de Supabase), cerrar sesión.
- 3 bugs de timing de auth encontrados y corregidos en vivo — ver
  `docs/modulos/frontend_login/decisiones.md` D-LOGIN-005 (esperar `perfilLoading` antes de montar
  el router), D-LOGIN-006 (logout automático en 401/404 de perfil + guard reactivo en
  `_authenticated.tsx`) y D-LOGIN-007 (redirect post-login con `window.location.href`, no
  `router.navigate()`). Los tres se dispararon porque `requireRole(...)` pasó de estar armado sin
  call sites (decisión original D-LOGIN-003) a tener call sites reales en las pantallas nuevas —
  ver detalle completo en ese archivo, no se repite acá.

### Explícitamente fuera de scope (sigue vigente)

- Registro libre de usuarios (`signUp`): el alta la sigue haciendo un `admin`/`superadmin` desde
  `usuarios/`, no un auto-registro público.

### Riesgos

Ninguno nuevo más allá de los 3 bugs de timing, ya corregidos y verificados en Chrome real. El
mapeo de errores de Supabase Auth en la invitación (429 → reintentar, otros → mensaje de Supabase)
fue verificado manualmente por el usuario contra Auth real, sin test automatizado — ver
`docs/modulos/usuarios/pendientes.md`.
