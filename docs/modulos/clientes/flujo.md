# Flujos — Clientes

Los 5 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en esta
sesión.

## Flujo 1 — Alta de cliente (`POST /clientes`)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` — `("admin", "gerencia",
   "lider_comercial", "comercial")` (`router.py:36`, `:53`).
2. `crear_cliente_endpoint` llama a `crear_cliente_para_endpoint(drogueria_id=usuario.drogueria_id,
   body=body, usuario_id=usuario.id)` (`router.py:55-57`).
3. `crear_cliente_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_cliente` (`service.py:180-181`).
4. `crear_cliente` arma la fila con `drogueria_id`, los campos del body,
   `created_by=usuario_id` y `updated_by=usuario_id`, e inserta directo — sin
   validaciones adicionales (`service.py:99-117`).
5. `repo.crear_cliente` hace el INSERT y devuelve la fila creada
   (`repository.py:44-45`).
6. El endpoint responde con `ClienteOut` (`router.py:50`, `response_model=ClienteOut`).

No hay validación de duplicados ni de unicidad de `codigo_interno` en este flujo:
`codigo_interno` ni siquiera aparece en el dict insertado por `crear_cliente`
(`service.py:104-116`) — su origen (¿autogenerado por trigger de base de datos?
¿cargado después por `imports/`?) no se pudo confirmar leyendo este módulo. Pendiente
de definición funcional — ver [`pendientes.md`](./pendientes.md).

## Flujo 2 — Baja de cliente (`DELETE /clientes/{id}`)

1. El router exige `require_roles(*_ROLES_ELIMINACION)` — `("admin", "gerencia")`, más
   restrictivo que `_ROLES_ESCRITURA` (`router.py:37`, `:83`).
2. `eliminar_cliente_endpoint` llama a `eliminar_cliente_para_endpoint(cliente_id=cliente_id,
   drogueria_id=usuario.drogueria_id, usuario_id=usuario.id)` (`router.py:85-87`).
3. `eliminar_cliente_para_endpoint` resuelve `get_service_client()` y delega en
   `eliminar_cliente` (`service.py:192-193`).
4. `eliminar_cliente` valida pertenencia con `obtener_cliente` (RN-CLIENTES-001,
   `service.py:143`) — `NotFoundError` si el cliente no existe o es de otra droguería.
5. `repo.soft_delete_cliente` hace el UPDATE de `deleted_at`/`deleted_by`/`activo=False`
   (`service.py:144`, `repository.py:52-59`, RN-CLIENTES-005).
6. El endpoint responde `204 No Content` (`router.py:80`, `status_code=204`).

## Flujo 3 — Gestión de contactos (`POST`/`PATCH /clientes/{id}/contactos[/{contacto_id}]`)

### Alta

1. El router exige `require_roles(*_ROLES_ESCRITURA)` e inyecta `user_client`
   (`router.py:104-105`).
2. El router valida pertenencia del cliente con `user_client` (RN-CLIENTES-007,
   `_validar_cliente_y_obtener_drogueria_id`, `router.py:107`).
3. `crear_contacto_endpoint` llama a `crear_contacto_para_endpoint(cliente_id=cliente_id,
   drogueria_id=drogueria_id, body=body)` (`router.py:108`) — `drogueria_id` es el
   resuelto por el router, no un campo del body.
4. `crear_contacto_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_contacto` (`service.py:196-199`).
5. `crear_contacto` **revalida** pertenencia con `service_client`, de forma
   independiente (RN-CLIENTES-002, `_validar_cliente_de_la_drogueria`,
   `service.py:150`).
6. `repo.crear_contacto` hace el INSERT (`service.py:151-163`,
   `repository.py:62-63`).
7. El endpoint responde con `ClienteContactoOut` (`router.py:100`).

### Edición

1. El router exige `require_roles(*_ROLES_ESCRITURA)` e inyecta `user_client`
   (`router.py:116-117`).
2. El router revalida pertenencia del cliente (RN-CLIENTES-007, `router.py:119`) —
   nota: valida que **el cliente** exista y pertenezca a la droguería, no que el
   contacto pertenezca a ese cliente.
3. `actualizar_contacto_endpoint` llama a
   `actualizar_contacto_para_endpoint(cliente_id=cliente_id, contacto_id=contacto_id,
   body=body)` (`router.py:120`).
4. `actualizar_contacto_para_endpoint` resuelve `get_service_client()` y delega en
   `actualizar_contacto` (`service.py:202-205`).
5. `actualizar_contacto` valida que el contacto encontrado por `contacto_id`
   pertenezca efectivamente a `cliente_id` (RN-CLIENTES-006, `service.py:173-175`) —
   esta es la única capa que cierra la validación cruzada contacto↔cliente; el paso 2
   por sí solo no la cubre.
6. `repo.actualizar_contacto` hace el UPDATE parcial (RN-CLIENTES-004,
   `service.py:176-177`, `repository.py:77-78`).
7. El endpoint responde con `ClienteContactoOut` (`router.py:111`).

### Lectura

`GET /clientes/{id}/contactos` usa solo `user_client` (RLS) — valida pertenencia con
RN-CLIENTES-007 (`router.py:96`) y luego llama a `listar_contactos(user_client,
cliente_id=cliente_id)` (`router.py:97`, `service.py:166-167`,
`repository.py:66-74`), sin pasar por `service_client` en ningún punto.

## Flujo 4 — Gestión de formato de documentos (cross-servicio con `services/extraccion`)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` e inyecta `user_client`
   (`router.py:162-163`).
2. El router resuelve `drogueria_id` con `user_client` (RN-CLIENTES-007,
   `router.py:165`).
3. `upsert_formato_documento_endpoint` llama a
   `upsert_formato_documento_para_endpoint(cliente_id=cliente_id,
   drogueria_id=drogueria_id, body=body, usuario_id=usuario.id)`
   (`router.py:166-168`).
4. `upsert_formato_documento_para_endpoint` resuelve `get_service_client()` —
   docstring explícito citado en D-CLIENTES-002 (`service.py:208-219`, cita textual en
   `:211-212`) — y delega en `upsert_formato_documento`.
5. `upsert_formato_documento` revalida pertenencia (RN-CLIENTES-002,
   `service.py:39`) y hace el upsert real por `UNIQUE(cliente_id, doc_type)`
   (RN-CLIENTES-003, `service.py:29-66`).
6. El endpoint responde con `ClienteFormatoDocumentoOut` (`router.py:159`).

**Consumo cross-servicio (fuera de este flujo HTTP, sin código compartido)**: al
procesar un documento, `services/extraccion/main.py` llama a `_resolver_formato_prompt`
(líneas 122-149), que hace `SELECT id, instrucciones_prompt FROM
cliente_formato_documentos WHERE cliente_id=? AND doc_type=? AND activo=True LIMIT 1`
(líneas 132-140, filtro `activo` en la línea 137). Si hay `instrucciones_prompt`, se
inyecta al prompt de Gemini (línea 221, invocación de `_resolver_formato_prompt`) — el
contenido que un usuario carga por `POST /clientes/{id}/formato-documentos` termina
influyendo directamente en el texto que la IA recibe al extraer datos de un documento
de ese cliente. Ver [`arquitectura.md`](./arquitectura.md) para el diagrama completo.

## Flujo 5 — Observaciones (`POST`/`GET /clientes/{id}/observaciones`)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` e inyecta `user_client`
   (`router.py:191-192`).
2. El router resuelve `drogueria_id` con `user_client` (RN-CLIENTES-007,
   `router.py:194`).
3. `crear_observacion_endpoint` llama a
   `crear_observacion_para_endpoint(cliente_id=cliente_id, drogueria_id=drogueria_id,
   body=body, usuario_id=usuario.id)` (`router.py:195-197`).
4. `crear_observacion_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_observacion` (`service.py:222-231`).
5. `crear_observacion` revalida pertenencia (RN-CLIENTES-002, `service.py:81`) y
   persiste con `creado_por=usuario_id` (`service.py:83-92`,
   `repository.py:129-130`).
6. El endpoint responde con `ClienteObservacionOut` (`router.py:184`).

No hay edición ni borrado de observaciones en todo el módulo: `repository.py` no tiene
funciones de update/delete para `cliente_observaciones`, y `router.py` no expone esos
verbos para este sub-recurso.
