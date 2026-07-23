# Casos de uso — Clientes

Los 12 endpoints montados en `services/presupuestacion/main.py:48`
(`app.include_router(clientes_router, tags=["clientes"])`), sin prefijo adicional.

Roles: `_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")`,
`_ROLES_ELIMINACION = ("admin", "gerencia")`, `_ROLES_LECTURA = ("superadmin", "admin",
"gerencia", "lider_comercial", "comercial", "compras")` (`router.py:36-38`).

## `GET /clientes`

- **Quién puede llamarlo**: los 6 roles de `_ROLES_LECTURA` (`router.py:44`).
- **Función**: `listar_clientes_endpoint`, con `activo: bool | None` opcional como
  query param.
- **Cliente Supabase**: `user_client` (con RLS).
- **Archivo**: `router.py:41-47`.

## `POST /clientes`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:53`).
- **Función**: `crear_cliente_endpoint`. Reglas: ninguna validación de negocio
  adicional más allá de tipado Pydantic — ver Flujo 1 en [`flujo.md`](./flujo.md).
- **Cliente Supabase**: `service_client` (sin RLS, vía `crear_cliente_para_endpoint`).
- **Archivo**: `router.py:50-57`.

## `GET /clientes/{cliente_id}`

- **Quién puede llamarlo**: `_ROLES_LECTURA` (`router.py:63`).
- **Función**: `obtener_cliente_endpoint`. Aplica RN-CLIENTES-001.
- **Cliente Supabase**: `user_client`.
- **Archivo**: `router.py:60-66`.

## `PATCH /clientes/{cliente_id}`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:73`).
- **Función**: `actualizar_cliente_endpoint`. Aplica RN-CLIENTES-001 (pertenencia) y
  RN-CLIENTES-004 (actualización parcial).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:69-77`.

## `DELETE /clientes/{cliente_id}`

- **Quién puede llamarlo**: `_ROLES_ELIMINACION` — más restrictivo que el resto de
  escritura, excluye `lider_comercial` y `comercial` (`router.py:83`).
- **Función**: `eliminar_cliente_endpoint`. Aplica RN-CLIENTES-001 y RN-CLIENTES-005
  (soft-delete).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:80-87`.

## `GET /clientes/{cliente_id}/contactos`

- **Quién puede llamarlo**: `_ROLES_LECTURA` (`router.py:93`).
- **Función**: `listar_contactos_endpoint`. Aplica RN-CLIENTES-007 (validación de
  pertenencia del cliente).
- **Cliente Supabase**: `user_client` únicamente — sin `service_client` en ningún
  punto de este endpoint.
- **Archivo**: `router.py:90-97`.

## `POST /clientes/{cliente_id}/contactos`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:104`).
- **Función**: `crear_contacto_endpoint`. Aplica RN-CLIENTES-007 (router) y
  RN-CLIENTES-002 (service, revalidación).
- **Cliente Supabase**: `user_client` para la validación previa (`router.py:107`) +
  `service_client` para el INSERT (`crear_contacto_para_endpoint`, RN-CLIENTES-008).
- **Archivo**: `router.py:100-108`.

## `PATCH /clientes/{cliente_id}/contactos/{contacto_id}`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:116`).
- **Función**: `actualizar_contacto_endpoint`. Aplica RN-CLIENTES-007 (router,
  pertenencia del cliente) y RN-CLIENTES-006 (service, pertenencia del contacto a ese
  cliente) y RN-CLIENTES-004 (parcial).
- **Cliente Supabase**: `user_client` + `service_client` (RN-CLIENTES-008).
- **Archivo**: `router.py:111-120`.

## `GET /clientes/{cliente_id}/formato-documentos`

- **Quién puede llamarlo**: `_ROLES_LECTURA` (`router.py:148`).
- **Función**: `listar_formato_documentos_endpoint`. Aplica RN-CLIENTES-007.
- **Cliente Supabase**: `user_client` únicamente.
- **Archivo**: `router.py:142-152`.

## `POST /clientes/{cliente_id}/formato-documentos`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:162`).
- **Función**: `upsert_formato_documento_endpoint`. Aplica RN-CLIENTES-007 (router),
  RN-CLIENTES-002 (service) y RN-CLIENTES-003 (upsert real).
- **Cliente Supabase**: `user_client` + `service_client` — docstring explícito de por
  qué (D-CLIENTES-002, `service.py:211-212`).
- **Archivo**: `router.py:155-168`.

## `GET /clientes/{cliente_id}/observaciones`

- **Quién puede llamarlo**: `_ROLES_LECTURA` (`router.py:177`).
- **Función**: `listar_observaciones_endpoint`. Aplica RN-CLIENTES-007.
- **Cliente Supabase**: `user_client` únicamente.
- **Archivo**: `router.py:171-181`.

## `POST /clientes/{cliente_id}/observaciones`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA` (`router.py:191`).
- **Función**: `crear_observacion_endpoint`. Aplica RN-CLIENTES-007 (router) y
  RN-CLIENTES-002 (service).
- **Cliente Supabase**: `user_client` + `service_client`.
- **Archivo**: `router.py:184-197`.

## Consumidores cross-servicio (con evidencia)

Ningún módulo de `presupuestacion/` **importa** `clientes/` salvo `main.py`
(confirmado por grep en esta sesión). Fuera de ese Python:

- `services/extraccion/routers/clientes.py:29-54` (`listar_activos`): `GET
  /api/clientes` de `services/extraccion` consulta la tabla `clientes` directo
  (`.eq("activo", True)`, línea 47) para el selector de cliente en el formulario de
  carga de documentos.
- `services/extraccion/main.py:122-149` (`_resolver_formato_prompt`), invocada desde
  el flujo de `POST /procesar` (línea 221): consulta `cliente_formato_documentos`
  directo (`.eq("activo", True)`, línea 137) para inyectar `instrucciones_prompt` al
  prompt de Gemini.
- `services/presupuestacion/imports/repository.py:141-185`: CRUD directo sobre
  `clientes` para importación masiva por `codigo_interno`, dentro del propio backend
  de `presupuestacion/` pero sin pasar por `clientes/repository.py`.

Se descartó `procesos_comerciales_client.py` como consumidor de este módulo: 0
matches en el grep de esta sesión sobre las 4 tablas (`clientes`,
`cliente_contactos`, `cliente_formato_documentos`, `cliente_observaciones`).
