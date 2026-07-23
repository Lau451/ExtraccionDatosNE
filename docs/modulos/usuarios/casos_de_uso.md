# Casos de uso — Usuarios

Los 7 endpoints (antes 4) montados en `services/presupuestacion/main.py:54`
(`app.include_router(usuarios_router, tags=["usuarios"])`), sin prefijo adicional.

## `GET /usuarios`

- **Quién puede llamarlo**: cualquier usuario autenticado con una fila válida en
  `usuarios` — sin restricción de rol (`router.py:27`, `Depends(get_current_user)`, sin
  `require_roles`).
- **Reglas que aplican**: ninguna regla de negocio de este módulo (no pasa por
  `service.py`). El alcance de filas devueltas depende de la policy RLS `usuarios_sel`
  (`docs/schema/rls_final.sql:117`) — ver [`base_de_datos.md`](./base_de_datos.md) y
  [`flujo.md`](./flujo.md) Flujo 6.
- **Archivo**: `services/presupuestacion/usuarios/router.py:25-30`.

## `GET /usuarios/{usuario_id}`

- **Quién puede llamarlo**: igual que el anterior — cualquier usuario autenticado, sin
  restricción de rol (`router.py:36`).
- **Reglas que aplican**: ninguna regla de negocio propia; `NotFoundError` si el `id` no
  existe o si RLS lo oculta (`router.py:40-41`) — ambos casos son indistinguibles desde
  la respuesta HTTP (404 en ambos).
- **Archivo**: `services/presupuestacion/usuarios/router.py:33-42`.

## `POST /usuarios`

- **Quién puede llamarlo**: solo `superadmin` o `admin`
  (`Depends(require_roles("superadmin", "admin"))`, `router.py:47`).
- **Reglas que aplican**: RN-USUARIOS-001 a 007 y RN-USUARIOS-013 (ver
  [`reglas.md`](./reglas.md)) — incluye que un `admin` no puede crear ni `superadmin` ni
  `admin` (RN-USUARIOS-002, endurecida en esta sesión), que la `drogueria_id` efectiva
  depende del rol del creador, y que el alta ahora es por invitación de email
  (RN-USUARIOS-013), no por password directa.
- **Archivo**: `services/presupuestacion/usuarios/router.py:45-49`.

## `PATCH /usuarios/{usuario_id}/rol`

- **Quién puede llamarlo**: solo `superadmin` o `admin`
  (`Depends(require_roles("superadmin", "admin"))`, `router.py:56`).
- **Reglas que aplican**: RN-USUARIOS-008 a 012 y RN-USUARIOS-014/015 (ver
  [`reglas.md`](./reglas.md)) — incluye la prohibición de cambiar rol desde/hacia
  `superadmin` o `sistema` (endurecida en esta sesión), la restricción de tenant para
  `admin`, la imposibilidad de auto-modificarse el rol, y la restricción de que solo
  `superadmin` promueva a `admin`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:52-58`.

## `PATCH /usuarios/{usuario_id}/activo` — **[NUEVO]**

- **Quién puede llamarlo**: solo `superadmin` o `admin`
  (`Depends(require_roles("superadmin", "admin"))`, `router.py:65`).
- **Reglas que aplican**: RN-USUARIOS-016 a 021 (ver [`reglas.md`](./reglas.md)) — mismo
  alcance de autorización que el cambio de rol (superadmin/admin, tenant para admin,
  protección de superadmin/sistema, no auto-modificación), más el efecto real del campo
  `activo`, que se aplica recién en el próximo request del usuario afectado a través de
  `get_current_user` (RN-USUARIOS-021).
- **Body**: `UsuarioActivoUpdate { activo: bool }`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:61-67`.

## `PATCH /usuarios/me` — **[NUEVO]**

- **Quién puede llamarlo**: cualquier usuario autenticado, sobre su propio perfil
  únicamente (`Depends(get_current_user)`, `router.py:73`, sin `require_roles`).
- **Reglas que aplican**: RN-USUARIOS-028 (ver [`reglas.md`](./reglas.md)) — sin chequeo
  de rol; la restricción de alcance es estructural (el `usuario_id` sale del token, no
  de la URL), no una regla de negocio explícita.
- **Body**: `UsuarioPerfilUpdate { nombre?: str, apellido?: str }` — campos omitidos no
  se tocan.
- **Archivo**: `services/presupuestacion/usuarios/router.py:70-75`.

## `DELETE /usuarios/{usuario_id}` — **[NUEVO]**

- **Quién puede llamarlo**: solo `superadmin` o `admin`
  (`Depends(require_roles("superadmin", "admin"))`, `router.py:81`).
- **Reglas que aplican**: RN-USUARIOS-022 a 027 (ver [`reglas.md`](./reglas.md)) — mismo
  alcance de autorización que `cambiar_activo`, más el mapeo de error si el usuario tiene
  actividad asociada por FK (`ConflictError` 409 en vez de un error crudo de Auth,
  verificado empíricamente en esta sesión).
- **Respuesta**: `204 No Content` sin body.
- **Archivo**: `services/presupuestacion/usuarios/router.py:78-83`.

## Consumidores reales

**[MODIFICADO]**: a diferencia de la revisión anterior, que no encontraba ningún
consumidor dentro del repositorio, el frontend **sí usa activamente** este módulo vía la
sección de gestión de usuarios (alta por invitación, cambio de rol,
activar/desactivar, edición de perfil propio, eliminación) — confirmado por la
existencia y el propósito explícito de la migración
`supabase/migrations/0007_apellido_y_planes.sql:4-5`
("Soporte de schema para el módulo de autenticación/gestión de usuarios completo:
invitación por email, 'Mi cuenta' [...]"). Sigue sin haber, dentro de
`services/presupuestacion/`, ningún `service.py` de otro módulo de negocio que importe
de `usuarios/` (confirmado igual que antes) — el consumo es exclusivamente desde el
frontend, no desde otro módulo del backend.
