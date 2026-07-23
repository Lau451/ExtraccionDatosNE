# Proposal: Gestión de usuarios (Admin/SuperAdmin)

**Estado: activo, no archivado.** Pantalla nueva, fuera de las 8 pantallas originales del MVP
(ver `frontend/PROGRESS.md`). Documentado el 2026-07-23, código ya implementado y verificado antes
de escribir este proposal.

## Intent

El módulo de usuarios (`services/presupuestacion/usuarios/`) creció de 4 a 7 endpoints en esta
sesión (invitación por email, activar/desactivar, autoservicio de perfil, eliminar — ver
`docs/modulos/usuarios/`) para soportar el ciclo de vida completo de una cuenta, pero no había
ninguna pantalla de frontend para que un `admin`/`superadmin` administrara usuarios de su
droguería (o de cualquiera, en el caso de `superadmin`). Sin esta pantalla, la única forma de
invitar o gestionar un usuario era llamar a la API a mano.

Se necesitaba: una pantalla protegida por rol que liste los usuarios visibles (según RLS/rol),
permita invitar usuarios nuevos por email, cambiar su rol, activar/desactivar y eliminar — todo
respetando exactamente las mismas restricciones que ya exige el backend, sin duplicar lógica de
negocio en el frontend más allá de ocultar opciones que el backend igual rechazaría.

## Scope

### Incluido
- Ruta protegida `/admin/usuarios` (`_authenticated.admin.usuarios.tsx`), con
  `beforeLoad: requireRole('admin', 'superadmin')`.
- `GestionUsuarios.tsx`: tabla de usuarios (nombre, rol, estado), con cambio de rol inline
  (`<select>`), activar/desactivar y eliminar (con `ConfirmDialog`).
- `InvitarUsuarioDialog.tsx`: modal de alta por invitación de email (email, nombre, apellido,
  rol; selector de empresa solo si quien invita es `superadmin`).
- Ocultamiento de opciones en el frontend que el backend igual rechazaría: no se puede
  cambiar rol/activo/eliminar sobre `superadmin`/`sistema` ni sobre el propio usuario logueado;
  solo `superadmin` ve `admin` como rol asignable.
- Consumo de `POST /usuarios`, `GET /usuarios`, `PATCH /usuarios/{id}/rol`,
  `PATCH /usuarios/{id}/activo`, `DELETE /usuarios/{id}` (`frontend/src/lib/api/usuarios.ts`).

### Explícitamente fuera de scope
- Cualquier regla de negocio nueva de backend — el módulo `usuarios/` ya existía completo antes de
  esta pantalla (ver `openspec/changes/archive/login-frontend/` actualización 2026-07-23); esta
  pantalla es wiring de frontend puro contra endpoints ya construidos y probados.
- Búsqueda, paginación o filtros sobre la tabla de usuarios — se lista todo lo que devuelve
  `GET /usuarios` (acotado por RLS) sin control adicional del lado cliente.
- Auditoría o historial de cambios visible en la UI — existe en el backend
  (`docs/modulos/usuarios/` no documenta un log de auditoría propio de este módulo; los eventos
  relevantes, si existen, pertenecen a otro módulo).

## Approach

Wiring directo contra los 5 endpoints de escritura + `GET /usuarios`, con TanStack Query
(`useQuery`/`useMutation`, invalidación de `['usuarios']` tras cada mutación exitosa). La
autorización real vive enteramente en el backend (`service.py`, ver `docs/modulos/usuarios/reglas.md`
RN-USUARIOS-001 a 028); el frontend replica el mismo criterio solo para no mostrar botones que
resultarían en un 403/422 — nunca es la única barrera.

## Riesgos

Ninguno relevante — sigue el mismo patrón de wiring ya validado por
`openspec/changes/archive/procesos-comerciales/` (frontend consumiendo un módulo de
`services/presupuestacion` ya construido y testeado). El riesgo real (mapeo de errores de
Supabase Auth en la invitación) es del backend, no de esta pantalla — documentado en
`openspec/changes/archive/login-frontend/`.
