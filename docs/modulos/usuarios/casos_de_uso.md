# Casos de uso — Usuarios

Los 7 endpoints (antes 4) montados en `services/presupuestacion/main.py:54`
(`app.include_router(usuarios_router, tags=["usuarios"])`), sin prefijo adicional.

## `GET /usuarios`

- **Quién puede llamarlo**: cualquier usuario autenticado con una fila válida en
  `usuarios` — sin restricción de rol (`router.py:28`, `Depends(get_current_user)`, sin
  `require_roles`).
- **Reglas que aplican**: ninguna regla de negocio de este módulo (no pasa por
  `service.py`). El alcance de filas devueltas depende de la policy RLS `usuarios_sel`
  (`docs/schema/rls_final.sql:117`) — ver [`base_de_datos.md`](./base_de_datos.md) y
  [`flujo.md`](./flujo.md) Flujo 6.
- **Archivo**: `services/presupuestacion/usuarios/router.py:26-31`.

## `GET /usuarios/{usuario_id}`

- **Quién puede llamarlo**: igual que el anterior — cualquier usuario autenticado, sin
  restricción de rol (`router.py:37`).
- **Reglas que aplican**: ninguna regla de negocio propia; `NotFoundError` si el `id` no
  existe o si RLS lo oculta (`router.py:41-42`) — ambos casos son indistinguibles desde
  la respuesta HTTP (404 en ambos).
- **Archivo**: `services/presupuestacion/usuarios/router.py:34-43`.

## `POST /usuarios`

- **Quién puede llamarlo**: solo `superadmin`, `admin` o `gerencia`
  (`Depends(require_roles(*ROLES_GESTION_USUARIOS))`, `router.py:48`,
  `service.py:12`).
- **Reglas que aplican**: RN-USUARIOS-001 a 007, RN-USUARIOS-013 y RN-USUARIOS-029 (ver
  [`reglas.md`](./reglas.md)) — incluye que ni `admin` ni `gerencia` pueden crear
  `superadmin` ni `admin` (RN-USUARIOS-002), que `gerencia` solo crea roles inferiores a
  `admin` (RN-USUARIOS-029), que la `drogueria_id` efectiva depende del rol del creador
  (forzada a la propia para `admin`/`gerencia`), y que el alta ahora es por invitación de
  email (RN-USUARIOS-013), no por password directa.
- **Archivo**: `services/presupuestacion/usuarios/router.py:46-50`.

## `PATCH /usuarios/{usuario_id}/rol`

- **Quién puede llamarlo**: solo `superadmin`, `admin` o `gerencia`
  (`Depends(require_roles(*ROLES_GESTION_USUARIOS))`, `router.py:57`).
- **Reglas que aplican**: RN-USUARIOS-008 a 012, RN-USUARIOS-014/015 y RN-USUARIOS-029
  (ver [`reglas.md`](./reglas.md)) — incluye la prohibición de cambiar rol desde/hacia
  `superadmin` o `sistema` (endurecida en esta sesión), la restricción de tenant para
  `admin` y `gerencia`, la imposibilidad de auto-modificarse el rol, la restricción de
  que solo `superadmin` promueva a `admin`, y que `gerencia` solo opera sobre y asigna
  roles inferiores a `admin`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:53-59`.

## `PATCH /usuarios/{usuario_id}/activo` — **[NUEVO]**

- **Quién puede llamarlo**: solo `superadmin`, `admin` o `gerencia`
  (`Depends(require_roles(*ROLES_GESTION_USUARIOS))`, `router.py:66`).
- **Reglas que aplican**: RN-USUARIOS-016 a 021 y RN-USUARIOS-029 (ver
  [`reglas.md`](./reglas.md)) — mismo alcance de autorización que el cambio de rol
  (superadmin/admin/gerencia, tenant para admin y gerencia, gerencia solo sobre roles
  inferiores a admin, protección de superadmin/sistema, no auto-modificación), más el efecto real del campo
  `activo`, que se aplica recién en el próximo request del usuario afectado a través de
  `get_current_user` (RN-USUARIOS-021).
- **Body**: `UsuarioActivoUpdate { activo: bool }`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:62-68`.

## `PATCH /usuarios/me` — **[NUEVO]**

- **Quién puede llamarlo**: cualquier usuario autenticado, sobre su propio perfil
  únicamente (`Depends(get_current_user)`, `router.py:74`, sin `require_roles`).
- **Reglas que aplican**: RN-USUARIOS-028 (ver [`reglas.md`](./reglas.md)) — sin chequeo
  de rol; la restricción de alcance es estructural (el `usuario_id` sale del token, no
  de la URL), no una regla de negocio explícita.
- **Body**: `UsuarioPerfilUpdate { nombre?: str, apellido?: str }` — campos omitidos no
  se tocan.
- **Archivo**: `services/presupuestacion/usuarios/router.py:71-76`.

## `DELETE /usuarios/{usuario_id}` — **[NUEVO]**

- **Quién puede llamarlo**: solo `superadmin`, `admin` o `gerencia`
  (`Depends(require_roles(*ROLES_GESTION_USUARIOS))`, `router.py:82`).
- **Reglas que aplican**: RN-USUARIOS-022 a 027 y RN-USUARIOS-029 (ver [`reglas.md`](./reglas.md)) — mismo
  alcance de autorización que `cambiar_activo`, más el mapeo de error si el usuario tiene
  actividad asociada por FK (`ConflictError` 409 en vez de un error crudo de Auth,
  verificado empíricamente en esta sesión).
- **Respuesta**: `204 No Content` sin body.
- **Archivo**: `services/presupuestacion/usuarios/router.py:79-84`.

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
