# Specification: Gestión de usuarios (Admin/SuperAdmin)

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/routes/_authenticated.admin.usuarios.tsx` | Ruta `/admin/usuarios`, `beforeLoad: requireRole('admin', 'superadmin')`. |
| `frontend/src/features/gestion-usuarios/GestionUsuarios.tsx` | Tabla de usuarios + orquestación de mutaciones (`cambiarRolUsuario`, `cambiarActivoUsuario`, `eliminarUsuario`). |
| `frontend/src/features/gestion-usuarios/InvitarUsuarioDialog.tsx` | Modal de alta por invitación de email. |
| `frontend/src/lib/api/usuarios.ts` | `listarUsuarios`, `invitarUsuario`, `cambiarRolUsuario`, `cambiarActivoUsuario`, `eliminarUsuario`. |
| `services/presupuestacion/usuarios/` | Backend consumido, ya existente y documentado en `docs/modulos/usuarios/` (no se toca en este change). |

## Comportamiento observable

### Roles asignables desde esta pantalla

`ROLES_BASE = ['gerencia', 'lider_comercial', 'comercial', 'compras']`. Si quien mira es
`superadmin`, se agrega `'admin'` al principio (`rolesAsignables`). Refleja en el frontend la
misma restricción que ya aplica el backend (RN-USUARIOS-002/RN-USUARIOS-015: solo `superadmin`
puede crear o promover a `admin`) — el frontend no permite construir un request que el backend de
todas formas rechazaría.

### Usuarios no editables desde la tabla

Una fila queda sin acciones de rol/activo/eliminar (`noEditable = esProtegido || esUnoMismo`) si:
- `usuario.rol` es `superadmin` o `sistema` (`esProtegido`) — mismo criterio que
  RN-USUARIOS-009/019/025 del backend.
- `usuario.id === perfil.id` (`esUnoMismo`) — mismo criterio que RN-USUARIOS-014/017/023
  (auto-modificación bloqueada).

El `<select>` de rol siempre incluye el rol actual del usuario en las opciones, aunque no esté en
`rolesAsignables` (por ejemplo, un `admin` viendo la fila de otro `admin` existente) — evita que el
`<select>` muestre un valor fuera de sus propias `<option>`.

### Selector de empresa en el modal de invitación — solo para `superadmin`

Un `admin` invita siempre dentro de su propia droguería: el backend fuerza `drogueria_id` del
creador sin mirar el body (RN-USUARIOS-003), así que el modal no pide elegir empresa. Un
`superadmin` no pertenece a ninguna droguería (`drogueria_id: null`), así que el body sí necesita
un `drogueria_id` explícito (RN-USUARIOS-004) — el modal muestra un `<select>` de empresas
(`listarDroguerias`, `enabled: open && esSuperadmin`, para no pedir el listado si no hace falta).

## Scenarios

### Scenario: admin invita un usuario dentro de su propia droguería
```
Given: un usuario autenticado con rol "admin"
When: abre "+ Invitar usuario", completa email/nombre/apellido/rol (sin elegir empresa — no se
  muestra el selector) y confirma
Then: POST /usuarios se envía sin drogueria_id en el body
  AND el backend fuerza drogueria_id = creador.drogueria_id (RN-USUARIOS-003)
  AND se invalida la query ["usuarios"] y el modal se cierra y limpia su estado
```

### Scenario: superadmin invita un usuario y debe elegir la empresa
```
Given: un usuario autenticado con rol "superadmin"
When: abre "+ Invitar usuario"
Then: se muestra el selector "Empresa", poblado por GET /droguerias
  AND el submit está bloqueado (required) hasta elegir una empresa
  AND al confirmar, POST /usuarios incluye drogueria_id explícito
```

### Scenario: admin no ve "admin" como rol asignable
```
Given: un usuario autenticado con rol "admin" abre "+ Invitar usuario" o el <select> de rol de
  una fila editable
When: se listan las opciones de rol
Then: solo aparecen "gerencia", "lider_comercial", "comercial", "compras"
  AND "admin" no está en la lista (refleja RN-USUARIOS-002/015 del backend)
```

### Scenario: superadmin sí ve "admin" como rol asignable
```
Given: un usuario autenticado con rol "superadmin"
When: abre "+ Invitar usuario" o el <select> de rol de una fila editable
Then: "admin" aparece como primera opción, además de los 4 roles base
```

### Scenario: fila de un superadmin o usuario sistema no tiene acciones
```
Given: la tabla incluye una fila con rol "superadmin" o "sistema"
When: se renderiza esa fila
Then: el rol se muestra como texto plano (sin <select>)
  AND no aparecen los botones "Desactivar"/"Reactivar" ni "Eliminar"
```

### Scenario: la propia fila del usuario logueado no tiene acciones
```
Given: la tabla incluye la fila del usuario actualmente autenticado (usuario.id === perfil.id)
When: se renderiza esa fila
Then: no aparecen acciones de cambio de rol, activar/desactivar ni eliminar sobre esa fila
  (refleja RN-USUARIOS-014/017/023: nadie puede auto-modificarse por esta vía)
```

### Scenario: desactivar y reactivar un usuario
```
Given: un admin/superadmin mira la fila de un usuario activo, editable
When: hace click en "Desactivar"
Then: PATCH /usuarios/{id}/activo con {activo: false}
  AND al resolver, se invalida ["usuarios"] y la fila pasa a mostrar "Desactivado" y el botón
  cambia a "Reactivar"
```

### Scenario: eliminar un usuario pide confirmación
```
Given: un admin/superadmin hace click en "Eliminar" sobre una fila editable
When: se abre el ConfirmDialog con el nombre completo del usuario
  AND el usuario confirma
Then: DELETE /usuarios/{id}
  AND al resolver, se invalida ["usuarios"] y se cierra el ConfirmDialog
```

### Scenario: eliminar un usuario con actividad asociada muestra el error del backend
```
Given: el usuario objetivo tiene eventos o historial de cambios asociados por FK
When: se confirma la eliminación
Then: el backend responde 409 (ConflictError, RN-USUARIOS-027)
  AND la pantalla muestra "No se pudo aplicar el cambio." (mensaje genérico, sin detalle del
  cuerpo del error — ver docs/modulos/frontend_login/pendientes.md sobre mensajes de error
  genéricos, mismo patrón en esta pantalla)
```

### Scenario: ruta protegida por rol
```
Given: un usuario autenticado con rol "comercial" (ni admin ni superadmin)
When: navega a /admin/usuarios
Then: requireRole('admin', 'superadmin') en beforeLoad rechaza el acceso (mismo mecanismo que
  documenta openspec/changes/archive/login-frontend/, actualización 2026-07-23)
```

## Verificación

Implementado y verificado en esta sesión contra el backend real de `usuarios/`
(`tests/usuarios/test_service.py` en verde — ver
`openspec/changes/archive/login-frontend/tasks.md`, sección de actualización 2026-07-23, que cubre
el módulo de backend consumido acá). No hay test automatizado propio de frontend para esta
pantalla (mismo patrón que el resto de `frontend/` — ver
`docs/modulos/frontend_login/pendientes.md` P1).
