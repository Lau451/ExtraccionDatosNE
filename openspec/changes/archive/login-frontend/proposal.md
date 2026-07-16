# Proposal: Login mínimo en frontend/

**Estado: archivado/completado.** Documentado retroactivamente el 2026-07-15 para adoptar la
convención de `openspec/` (ver `openspec/AGENTS.md`) — el código ya estaba implementado y
verificado antes de escribir este proposal.

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
