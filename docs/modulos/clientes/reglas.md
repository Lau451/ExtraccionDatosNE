# Reglas — Clientes

Todas las reglas fueron verificadas contra el código real (`service.py`, `router.py`) y
sus tests (`tests/clientes/test_service.py`) en esta sesión.

### RN-CLIENTES-001 — Un cliente solo es consultable/modificable si pertenece a la droguería del solicitante

- **Descripción**: `obtener_cliente` (service) busca el cliente por `id` y valida que
  su `drogueria_id` coincida con el del solicitante; si no coincide (o no existe), se
  trata igual: `NotFoundError`, sin distinguir un caso del otro.
- **Condición**: `cliente is None or cliente["drogueria_id"] != drogueria_id`.
- **Resultado**: `NotFoundError("No se encontró el cliente")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/service.py:126-130`.
- **Observaciones**: [IMPLEMENTADO]. Reutilizada tal cual por `actualizar_cliente`
  (`service.py:136`) y `eliminar_cliente` (`service.py:143`) como primer paso, antes de
  cualquier escritura. Verificada en
  `tests/clientes/test_service.py:222-227`
  (`test_obtener_cliente_de_otra_drogueria_lanza_not_found`).

### RN-CLIENTES-002 — Para sub-recursos, la pertenencia se valida con `ValidationError`, no `NotFoundError`

- **Descripción**: `_validar_cliente_de_la_drogueria`, usada por `upsert_formato_documento`,
  `crear_observacion` y `crear_contacto`, distingue explícitamente "no existe" de
  "existe pero es de otra droguería" con dos excepciones distintas — a diferencia de
  RN-CLIENTES-001, que colapsa ambos casos en `NotFoundError`.
- **Condición**: `cliente["drogueria_id"] != drogueria_id` (tras confirmar que el
  cliente existe).
- **Resultado**: `ValidationError("El cliente no pertenece a esta droguería")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/service.py:18-26`.
- **Observaciones**: [IMPLEMENTADO]. Si el cliente directamente no existe, la misma
  función levanta `NotFoundError("No se encontró el cliente")` (`service.py:22-23`).
  Verificada en `tests/clientes/test_service.py:122-149`
  (`test_upsert_formato_documento_cliente_de_otra_drogueria_falla`, espera
  `ValidationError`) y `tests/clientes/test_service.py:108-119`
  (`test_upsert_formato_documento_cliente_inexistente`, espera `NotFoundError`). Ver
  D-CLIENTES-004 en [`decisiones.md`](./decisiones.md) sobre la inconsistencia con
  RN-CLIENTES-001.

### RN-CLIENTES-003 — `upsert_formato_documento` es upsert real por `UNIQUE(cliente_id, doc_type)`

- **Descripción**: si ya existe una fila para ese `cliente_id`+`doc_type`, la actualiza;
  si no, la crea. No hay un endpoint separado de create vs update para este sub-recurso.
- **Condición**: `repo.buscar_formato_documento(client, cliente_id=..., doc_type=...)`
  devuelve una fila o `None`.
- **Resultado**: `repo.actualizar_formato_documento(...)` si existe
  (`service.py:53-56`), `repo.crear_formato_documento(...)` si no (`service.py:58-66`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/service.py:29-66` (docstring en
  `:37-38`, decisión de existente/nuevo en `:50-66`).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/clientes/test_service.py:31-51`
  (`test_upsert_formato_documento_crea_si_no_existe`),
  `tests/clientes/test_service.py:55-79`
  (`test_upsert_formato_documento_actualiza_si_ya_existe`, confirma que el `id` no
  cambia y el segundo upsert pisa el valor) y
  `tests/clientes/test_service.py:83-105`
  (`test_upsert_formato_documento_no_pisa_otro_doc_type`, confirma que un `doc_type`
  distinto no colisiona).

### RN-CLIENTES-004 — `actualizar_cliente`/`actualizar_contacto` son actualizaciones parciales

- **Descripción**: solo se pisan los campos enviados explícitamente en el body; los
  campos no incluidos en el `PATCH` no se tocan.
- **Condición**: cualquier llamada a `actualizar_cliente` o `actualizar_contacto`.
- **Resultado**: `body.model_dump(exclude_unset=True)` — `service.py:137` (cliente,
  con `updated_by` agregado después en `:138`) y `service.py:176` (contacto).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/service.py:137`, `:176`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/clientes/test_service.py:231-245`
  (`test_actualizar_cliente_solo_pisa_campos_enviados`) y
  `tests/clientes/test_service.py:318-339`
  (`test_actualizar_contacto_solo_pisa_campos_enviados`).

### RN-CLIENTES-005 — Eliminar un cliente es siempre soft-delete

- **Descripción**: no existe una vía en este módulo para borrar físicamente una fila de
  `clientes`. `DELETE /clientes/{id}` marca `deleted_at`, `deleted_by` y fuerza
  `activo=False`.
- **Condición**: cualquier llamada exitosa a `eliminar_cliente`.
- **Resultado**: `repo.soft_delete_cliente(client, cliente_id=cliente_id,
  usuario_id=usuario_id)` — UPDATE, nunca DELETE.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/repository.py:52-59`, invocado desde
  `services/presupuestacion/clientes/service.py:142-144`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/clientes/test_service.py:248-270`
  (`test_eliminar_cliente_soft_delete`, confirma `deleted_at`/`deleted_by`/`activo`
  tras el borrado y que `obtener_cliente` deja de encontrarlo).

### RN-CLIENTES-006 — Actualizar un contacto valida que pertenezca al `cliente_id` de la URL, no solo que exista

- **Descripción**: `actualizar_contacto` busca el contacto solo por `contacto_id`
  (`repository.py:81-85`, sin filtro de `cliente_id` en la query), por lo que la
  validación de pertenencia al `cliente_id` correcto se hace en Python después de
  traerlo.
- **Condición**: `contacto is None or contacto["cliente_id"] != cliente_id`.
- **Resultado**: `NotFoundError("No se encontró el contacto")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/service.py:173-175`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/clientes/test_service.py:296-315`
  (`test_actualizar_contacto_de_otro_cliente_lanza_not_found`, crea el contacto bajo
  `cliente_a` e intenta actualizarlo pasando `cliente_id=cliente_b["id"]`).

### RN-CLIENTES-007 — El router revalida pertenencia de sub-recursos de forma independiente de `service.py`

- **Descripción**: antes de llamar a cualquier función de `service.py` para los 3
  sub-recursos, `router.py` hace su propia consulta de pertenencia con `user_client`
  (con RLS), independiente de la que hace `service.py` con `service_client` (sin RLS).
- **Condición**: `_validar_cliente_y_obtener_drogueria_id(user_client, usuario,
  cliente_id)` — `SELECT id, drogueria_id FROM clientes WHERE id = cliente_id LIMIT 1`.
- **Resultado**: `NotFoundError("No se encontró el cliente")` si no hay fila
  (`router.py:133-134`); `ForbiddenError("El cliente no pertenece a tu droguería")` si
  `usuario.rol != "superadmin"` y la droguería no coincide (`router.py:137-138`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/clientes/router.py:123-139`.
- **Observaciones**: [IMPLEMENTADO]. A diferencia de RN-CLIENTES-001/002, esta
  validación exceptúa explícitamente al rol `superadmin` de la comparación de
  `drogueria_id` (`router.py:137`) — ver D-CLIENTES-004 en
  [`decisiones.md`](./decisiones.md) sobre la inconsistencia de excepciones entre las
  tres capas de validación de tenant.

### RN-CLIENTES-008 — Las escrituras de sub-recursos corren con `service_client`, tras resolver `drogueria_id` con `user_client`

- **Descripción**: para los 4 endpoints de escritura de sub-recursos, el router primero
  resuelve `drogueria_id` con `user_client` (vía RN-CLIENTES-007) y luego llama a un
  wrapper `*_para_endpoint` de `service.py`, que internamente vuelve a resolver
  `get_service_client()` — el cliente sin RLS usado para el INSERT/UPDATE real.
- **Condición**: cualquier `POST`/`PATCH` de contactos, formato-documentos u
  observaciones.
- **Resultado**: el router nunca pasa su `user_client` a `service.py`; cada wrapper
  `*_para_endpoint` obtiene su propio `service_client` (`service.py:180-231`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/clientes/router.py:107-108` (contactos, POST),
  `:165-168` (formato-documentos), `:194-197` (observaciones);
  `services/presupuestacion/clientes/service.py:180-231` (los wrappers).
- **Observaciones**: [IMPLEMENTADO]. Motivo explícito solo para
  `cliente_formato_documentos` — ver D-CLIENTES-002 en
  [`decisiones.md`](./decisiones.md).
