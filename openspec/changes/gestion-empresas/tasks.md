# Tasks: Gestión de empresas (SuperAdmin)

**Change:** gestion-empresas
**Estado:** activo (no archivado — pantalla nueva, fuera de las 8 originales del MVP)

---

## Backend (ya existente, consumido sin cambios en este change)

- [x] `services/presupuestacion/droguerias/` completo (5 endpoints, CRUD) — ver
      `docs/modulos/droguerias/`
- [x] `services/presupuestacion/planes/` — `GET /planes` (catálogo, sin CRUD) — ver
      `docs/modulos/planes/`
- [x] `supabase/migrations/0007_apellido_y_planes.sql` — soporte de schema para planes

## Frontend — routing

- [x] `frontend/src/routes/_authenticated.superadmin.empresas.tsx` — `requireRole('superadmin')`

## Frontend — pantalla

- [x] `frontend/src/features/gestion-empresas/GestionEmpresas.tsx` — tabla, mutaciones de
      plan/activa/eliminar
- [x] `FilaDrogueria` — `<select>` de plan (solo planes activos), botón suspender/reactivar,
      botón eliminar
- [x] `ConfirmDialog` para eliminar, con nombre de la empresa en la descripción
- [x] Mensaje de error de `eliminarMutation`/`actualizarMutation` visible sobre la tabla

## Frontend — creación

- [x] `frontend/src/features/gestion-empresas/CrearDrogueriaDialog.tsx` — alta de empresa,
      autoformato de CUIT (`formatearCuit`, `pattern` HTML)
- [x] `frontend/src/features/gestion-empresas/CrearPrimerAdminDialog.tsx` — invita admin fijo
      (`rol: 'admin'`) para la droguería de la fila, reusa `invitarUsuario`

## Frontend — API

- [x] `frontend/src/lib/api/droguerias.ts` — `listarDroguerias`, `crearDrogueria`,
      `actualizarDrogueria`, `eliminarDrogueria`
- [x] `frontend/src/lib/api/planes.ts` — `listarPlanes`

## Verificación

- [x] Backend verificado por tests (`tests/droguerias/test_service.py`, incluye eliminación con
      FK real), no específicos de esta pantalla sino del módulo consumido
- [ ] Sin test automatizado de frontend para esta pantalla (mismo patrón que el resto de
      `frontend/`)
- [ ] `planes/` sin tests automatizados en absoluto (no existe `tests/planes/`)

## Fuera de este change

- [ ] CRUD de planes (crear/editar planes) — no existe endpoint, se gestiona por SQL directo.
