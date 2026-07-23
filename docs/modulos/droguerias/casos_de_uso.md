# Casos de uso — Droguerías

Los 5 endpoints montados en `services/presupuestacion/main.py:55`
(`app.include_router(droguerias_router, tags=["droguerias"])`), sin prefijo adicional.

## `GET /droguerias`

- **Quién puede llamarlo**: cualquier usuario autenticado, cualquier rol
  (`Depends(get_current_user)`, sin `require_roles`) — el filtro real de qué filas ve
  cada uno lo hace RLS (`droguerias_sel`, RN-DROGUERIAS-006).
- **Función**: `listar_droguerias_endpoint`. Sin query params.
- **Cliente Supabase**: `user_client` (con RLS), consulta directo desde el router.
- **Archivo**: `router.py:17-24`.

## `GET /droguerias/{drogueria_id}`

- **Quién puede llamarlo**: cualquier usuario autenticado. Aplica RN-DROGUERIAS-006:
  si la fila no le pertenece (y no es `superadmin`), RLS hace que la query no la
  devuelva, y el router responde `NotFoundError` (no `ForbiddenError`) — no distingue
  "no existe" de "no te pertenece".
- **Función**: `obtener_drogueria_endpoint`.
- **Cliente Supabase**: `user_client`, consulta directo desde el router.
- **Archivo**: `router.py:27-36`.

## `POST /droguerias`

- **Quién puede llamarlo**: solo `superadmin` (`require_roles("superadmin")`,
  RN-DROGUERIAS-005).
- **Función**: `crear_drogueria_endpoint`. Aplica RN-DROGUERIAS-001 (formato de CUIT).
- **Cliente Supabase**: `service_client` (sin RLS, vía `crear_drogueria_para_endpoint`).
- **Archivo**: `router.py:39-43`.

## `PATCH /droguerias/{drogueria_id}`

- **Quién puede llamarlo**: solo `superadmin` (RN-DROGUERIAS-005).
- **Función**: `actualizar_drogueria_endpoint`. Aplica RN-DROGUERIAS-001 (si se envía
  `cuit`), RN-DROGUERIAS-002 (existencia) y RN-DROGUERIAS-003 (parcial). Es también el
  único camino para asignar `plan_id` — ver Flujo 2 en [`flujo.md`](./flujo.md).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:46-52`.

## `DELETE /droguerias/{drogueria_id}`

- **Quién puede llamarlo**: solo `superadmin` (RN-DROGUERIAS-005).
- **Función**: `eliminar_drogueria_endpoint`. Aplica RN-DROGUERIAS-002 (existencia) y
  RN-DROGUERIAS-004 (hard-delete con traducción de FK a `ConflictError`).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:55-60`.

## Consumidores

Ningún módulo de `presupuestacion/` importa `droguerias/` (confirmado por grep en esta
sesión). El frontend resuelve el alta del primer administrador de una empresa reusando
`POST /usuarios` con `drogueria_id` explícito — ver [`../usuarios/`](../usuarios/), no
se repite el detalle acá.
