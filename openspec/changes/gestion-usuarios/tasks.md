# Tasks: Gestión de usuarios (Admin/SuperAdmin)

**Change:** gestion-usuarios
**Estado:** activo (no archivado — pantalla nueva, fuera de las 8 originales del MVP)

---

## Backend (ya existente, consumido sin cambios en este change)

- [x] `services/presupuestacion/usuarios/` completo (7 endpoints) — ver
      `openspec/changes/archive/login-frontend/`, actualización 2026-07-23, y
      `docs/modulos/usuarios/`

## Frontend — routing

- [x] `frontend/src/routes/_authenticated.admin.usuarios.tsx` — `requireRole('admin', 'superadmin')`

## Frontend — pantalla

- [x] `frontend/src/features/gestion-usuarios/GestionUsuarios.tsx` — tabla, mutaciones de rol/activo/eliminar
- [x] `rolesAsignables` calculado según `perfil.rol` (agrega `admin` solo si `superadmin`)
- [x] `FilaUsuario` — oculta acciones para `superadmin`/`sistema` y para la propia fila del usuario logueado
- [x] `<select>` de rol incluye siempre el rol actual, aunque no esté en `rolesAsignables`
- [x] `ConfirmDialog` para eliminar, con nombre completo del usuario en la descripción

## Frontend — invitación

- [x] `frontend/src/features/gestion-usuarios/InvitarUsuarioDialog.tsx`
- [x] Selector de empresa condicional (`esSuperadmin`), con `GET /droguerias` solo si `open && esSuperadmin`
- [x] Mensaje de error de la mutación visible en el modal (`mutation.error.message`)

## Frontend — API

- [x] `frontend/src/lib/api/usuarios.ts` — `listarUsuarios`, `invitarUsuario`, `cambiarRolUsuario`,
      `cambiarActivoUsuario`, `eliminarUsuario`

## Verificación

- [x] Backend verificado por tests (`tests/usuarios/test_service.py`), no específicos de esta
      pantalla sino del módulo consumido
- [ ] Sin test automatizado de frontend para esta pantalla (mismo patrón que el resto de
      `frontend/`)

## Fuera de este change

- [ ] Búsqueda/paginación/filtros sobre la tabla de usuarios — no implementado, no pedido para
      esta pantalla.
