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
