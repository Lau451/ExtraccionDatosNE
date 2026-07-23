# Tasks: Login mínimo en frontend/

**Change:** login-frontend
**Estado:** completado y archivado
**Commit:** `cdec6a8` — feat: agregar login minimo en frontend con guard de rutas (2026-07-15 09:29)

---

## Setup

- [x] Instalar `@supabase/supabase-js`
- [x] Crear `frontend/.env` (gitignored) con `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_PRESUPUESTACION_API_URL`
- [x] Actualizar `frontend/.env.example`
- [x] Agregar `.env` explícito a `frontend/.gitignore` (tenía `*.local` pero no `.env` a secas)

## Cliente Supabase y fetch wrapper

- [x] `frontend/src/lib/supabase.ts` — cliente singleton, uso exclusivo auth
- [x] `frontend/src/lib/api/presupuestacion.ts` — fetch wrapper con Bearer token, error shape `{detail}`

## Auth context y UI

- [x] `frontend/src/features/auth/AuthContext.tsx` — sesión + perfil (rol) + signIn/signOut
- [x] `frontend/src/features/auth/LoginForm.tsx`
- [x] `frontend/src/features/auth/routeGuards.ts` — `requireAuth` en uso; `requireRole(...)` armado sin call site

## Routing

- [x] `frontend/src/routes/login.tsx` — pública, `?redirect=`
- [x] `frontend/src/routes/_authenticated.tsx` — layout pathless, `beforeLoad: requireAuth`, mueve el Sidebar acá
- [x] `frontend/src/routes/_authenticated.index.tsx` — reemplaza `routes/index.tsx`
- [x] `frontend/src/routes/__root.tsx` — `createRootRouteWithContext<{auth}>()`
- [x] `frontend/src/main.tsx` — `InnerApp` con `useAuth()` inyectando contexto al router

## Integración

- [x] `frontend/src/features/shell/Sidebar.tsx` — perfil real + logout, reemplaza placeholder

## Verificación

- [x] Verificado en Chrome real (no solo compiló): guard, login, `GET /usuarios/{id}` con JWT,
      Sidebar con nombre real, persistencia tras reload, logout
- [x] Usuario de prueba creado y borrado con autorización explícita (sin basura en BD)
- [x] `npm run build` NO se corrió (regla del usuario) — validado con `vite dev` + prueba real
- [x] Commit `cdec6a8` — working tree limpio

## Archivado

- [x] Change movido a `openspec/changes/archive/login-frontend/` (retroactivo, 2026-07-15, al
      adoptar la convención de `openspec/AGENTS.md`)

---

## Actualización 2026-07-23 — invitación, reset, accept-invite, mi cuenta

### Backend — invitación por email

- [x] `usuarios/models.py` — `UsuarioCreate` sin `password`, con `apellido` obligatorio;
      `UsuarioActivoUpdate`, `UsuarioPerfilUpdate` nuevos
- [x] `usuarios/repository.py` — `invitar_usuario_auth` (reemplaza `crear_usuario_auth`), mapeo
      429→`ConflictError`/otros→`ValidationError`; `actualizar_activo`, `actualizar_perfil`,
      `eliminar_usuario_auth`
- [x] `usuarios/service.py` — `crear_usuario` usa invitación; `cambiar_activo`,
      `eliminar_usuario`, `actualizar_perfil_propio` nuevas, con auto-modificación bloqueada y
      protección de `superadmin`/`sistema`
- [x] `usuarios/router.py` — `PATCH /usuarios/{id}/activo`, `PATCH /usuarios/me`,
      `DELETE /usuarios/{id}` nuevos
- [x] `core/config.py` — setting `frontend_url` para `redirect_to` de la invitación
- [x] `core/auth.py` — `get_current_user` rechaza con 401 si `activo=False`
- [x] `supabase/migrations/0007_apellido_y_planes.sql` — columna `apellido`, soporte de schema
- [x] Tests `tests/usuarios/test_service.py` en verde (invitación, cambiar_activo,
      eliminar_usuario con actividad asociada, actualizar_perfil_propio)

### Frontend — reset-password, accept-invite, mi cuenta

- [x] `frontend/src/features/auth/useSessionFromLink.ts` — detecta sesión temporal de link de
      Supabase (recovery/invite)
- [x] `frontend/src/features/auth/SetPasswordForm.tsx` — formulario compartido de nueva
      contraseña
- [x] `frontend/src/routes/reset-password.tsx` — solicitar reset + `SetPasswordForm`
- [x] `frontend/src/routes/accept-invite.tsx` — activar invitación + `SetPasswordForm`, mensaje
      de link inválido/expirado
- [x] `frontend/src/routes/_authenticated.mi-cuenta.tsx` + `frontend/src/features/mi-cuenta/MiCuenta.tsx`
      — editar nombre/apellido, cambiar contraseña, cambiar email, cerrar sesión
- [x] `frontend/src/lib/api/usuarios.ts` — `actualizarPerfilPropio`, `invitarUsuario`, y el resto
      de funciones consumidas por `gestion-usuarios/`

### Bugs de timing encontrados y corregidos en vivo

- [x] D-LOGIN-005 — `AuthContext` expone `perfilLoading`; `main.tsx` espera
      `loading || perfilLoading` antes de montar el router (reload directo a ruta con
      `requireRole`)
- [x] D-LOGIN-006 — `signOut()` automático en 401/404 de perfil + `useEffect` reactivo en
      `_authenticated.tsx` (usuario desactivado/borrado con sesión de Supabase aún vigente)
- [x] D-LOGIN-007 — redirect post-login con `window.location.href` en vez de
      `router.navigate()` (login→redirect a ruta con `requireRole`)

### Verificación

- [x] Verificado en Chrome real con un superadmin real: reload directo a `/superadmin/empresas`,
      login→redirect a ruta protegida, desactivación/borrado con sesión vigente
- [x] Tests de backend en verde (`tests/usuarios/test_service.py`)
- [x] Mapeo de errores 429/otros de la invitación verificado manualmente contra Supabase Auth
      real (sin test automatizado)
- [x] `docs/modulos/usuarios/`, `docs/modulos/frontend_login/`, `docs/modulos/frontend_mi_cuenta/`
      actualizados y releídos contra el código real en esta sesión

### Re-archivado

- [x] Change reabierto desde `archive/` para documentar esta actualización, y vuelto a mover a
      `openspec/changes/archive/login-frontend/` al cerrar (2026-07-23)
