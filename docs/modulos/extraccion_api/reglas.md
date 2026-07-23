# Reglas — API & Persistencia (legacy)

Todas las reglas fueron verificadas contra el código real (`main.py`, `routers/*.py`,
`supabase_client.py`, `persistent_output.py`, `persistent_chunking.py`,
`background_tasks.py`, `auth.py`, `procesos_comerciales_client.py`) y sus tests en esta
sesión.

### RN-EXTRACCIONAPI-001 — Deduplicación de documentos por SHA256 vía RPC con lock

- **Descripción**: antes de procesar un archivo, se calcula su SHA256 y se consulta la
  RPC `reserve_extraction`, que hace `SELECT FOR UPDATE` server-side para evitar que dos
  requests simultáneos del mismo archivo generen dos extracciones paralelas.
- **Condición**: cada request a `POST /procesar`, inmediatamente después de guardar el
  archivo en disco.
- **Resultado**: si `reserve_extraction` retorna un UUID (existe un `extraction_result`
  `status='completed'` con ese hash), la request corta con HTTP 409 antes de invocar a
  `extraccion_ia` (`main.py:206-215`). Si retorna `None` (sin duplicado, o el registro
  existente es `partial`/`failed`), se permite el procesamiento
  (`persistent_output.py:56-71`, docstring).
- **Prioridad**: Alta.
- **Archivo**: `persistent_output.py:34-103` (`calcular_sha256`,
  `buscar_duplicado_con_lock`), `main.py:200-215`.
- **Observaciones**: [IMPLEMENTADO]. Si la RPC lanza excepción (ej. Supabase caído), se
  loguea `warning` y se procede **sin** verificación de duplicados
  (`persistent_output.py:97-103`) — la deduplicación es best-effort, nunca bloquea la
  carga por un fallo de infraestructura. Confirmado por
  `tests/test_persistent_output.py:163-177`.

### RN-EXTRACCIONAPI-002 — Resolución de `drogueria_id` única, con fallback no determinístico

- **Descripción**: toda persistencia en el schema nuevo de `presupuestacion/`
  (`extraction_results`, `processing_sessions`, `chunk_results`) requiere `drogueria_id`
  (`NOT NULL`), pero este backend no modela ese concepto. `resolver_drogueria_id_unica`
  resuelve el valor con prioridad: variable de entorno `DROGUERIA_ID` (determinística) →
  fallback a `SELECT id FROM droguerias LIMIT 1` sin `ORDER BY` (no determinístico si hay
  más de una fila) → cacheado en proceso para toda la vida del proceso.
- **Condición**: cualquier función de persistencia que necesite `drogueria_id`
  (`crear_sesion`, `guardar_chunk`, `persistir_output_final`,
  `validar_proceso_comercial_id`, `listar_nombres_procesos_comerciales`,
  `routers/clientes.py:listar_activos`).
- **Resultado**: cita literal del docstring (`supabase_client.py:116-124`):

  > "Prioridad: variable de entorno DROGUERIA_ID si está configurada (determinística, sin
  > ambigüedad posible). Si no está seteada, hace fallback a la primera fila de
  > `droguerias` (SELECT ... LIMIT 1 sin filtro) — válido HOY porque esta base tiene una
  > sola droguería, pero deja de ser seguro apenas se agregue una segunda: sin ORDER BY,
  > Postgres puede devolver cualquiera de las dos de forma no determinística, y el
  > resultado se cachea para toda la vida del proceso."

- **Prioridad**: Alta.
- **Archivo**: `supabase_client.py:108-150`.
- **Observaciones**: [IMPLEMENTADO], riesgo documentado por el propio autor del código.
  Confirmado por `tests/test_supabase_client.py:161-234`
  (`test_usa_droguria_id_de_env_sin_consultar_la_tabla`,
  `test_resuelve_y_cachea_via_fallback_sin_env`). Ver D-EXTRACCIONAPI-003 en
  [`decisiones.md`](./decisiones.md) y P1 en [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONAPI-003 — Persistencia parcial: solo metadata, nunca las filas extraídas

- **Descripción**: `persistir_output_final` inserta en `extraction_results` únicamente
  metadata del documento (nombre, hash, tipo, cantidad de filas, path del CSV, status) —
  las filas de datos extraídas (`rows`) nunca se envían a Supabase.
- **Condición**: cada llamada exitosa a `persistir_output_final`.
- **Resultado**: cita literal (`persistent_output.py:9-12`, docstring de módulo):

  > "Todas las funciones retornan None (sin propagar excepcion) si el cliente Supabase no
  > esta disponible. El CSV en disco es siempre la fuente de verdad: las filas extraidas
  > (`rows`) NO se persisten en Supabase, solo la metadata del documento.
  > `presupuestacion/extraccion/` lee las filas parseando `csv_disk_path` del disco."

  El payload de INSERT (`persistent_output.py:200-210`) confirma esto: no incluye la
  clave `rows` en ningún punto.
- **Prioridad**: Alta.
- **Archivo**: `persistent_output.py:106-244` (`persistir_output_final`).
- **Observaciones**: [IMPLEMENTADO]. `rows` sí se valida (debe ser no vacío, y genera
  `WARNING` si supera `_WARN_ROW_COUNT=50_000`, `persistent_output.py:26,163-179`) pero
  únicamente para decidir si el documento es válido — el array en sí se descarta después
  de la validación.

### RN-EXTRACCIONAPI-004 — Retry con backoff exponencial en la persistencia de background

- **Descripción**: `_retry_persist` reintenta `persistir_output_final` hasta 3 veces
  totales, con espera exponencial entre intentos fallidos.
- **Condición**: cualquier excepción (incluida `persistir_output_final` retornando `None`
  sin excepción, tratado como error vía `RuntimeError` sintético,
  `background_tasks.py:99-100`) durante un intento.
- **Resultado**: esquema real con `max_attempts=3` (`background_tasks.py:36`, default):
  intento 0 falla → `sleep(2**1=2s)` → intento 1 falla → `sleep(2**2=4s)` → intento 2
  falla → se registra `ERROR` final y se abandona, **sin** un tercer `sleep` de 8s
  (`background_tasks.py:102-137`). Confirmado exactamente por
  `tests/test_background_tasks.py:124-150`
  (`test_retry_persist_backoff_exponencial`, `assert sleep_args == [2, 4]`, 2 sleeps
  exactos). El docstring de módulo (`background_tasks.py:5-6`) describe "2s, 4s, 8s entre
  intentos" — esto es inexacto respecto del comportamiento real verificado por el test:
  solo hay 2 esperas (2s y 4s) antes del intento final, nunca una espera de 8s. Ver P2 en
  [`pendientes.md`](./pendientes.md).
- **Prioridad**: Alta.
- **Archivo**: `background_tasks.py:39-150` (`_retry_persist`).
- **Observaciones**: [IMPLEMENTADO]. Tras agotar los 3 intentos, el error se loguea con
  `logger.error` incluyendo `session_id`, `sha256` (truncado) y `source_filename` "para
  reconciliación manual" (`background_tasks.py:107-116`), y — si `session_id` no es
  `None` — se cierra la sesión con `status="failed"` y `error_msg=str(exc)`
  (`background_tasks.py:117-122`). La excepción **nunca** se propaga al caller
  (`schedule_persist_output` corre como `BackgroundTask` de FastAPI, después de que la
  respuesta HTTP ya fue enviada — `main.py:269-279`); el único rastro del fallo es el log
  `ERROR` y, si existía sesión, la fila `processing_sessions` con `status="failed"`. Si
  no hay `session_id` (por ejemplo, `crear_sesion` falló antes), el fallo de persistencia
  queda **solo en el log de aplicación**, sin ningún registro en base de datos. Ver P1 en
  [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONAPI-005 — Fail-fast de `tipo="ordenes"` antes de cualquier I/O

- **Descripción**: el pipeline de Orden de Compra no está implementado; `/procesar`
  rechaza ese tipo antes de guardar el archivo o invocar cualquier lógica.
- **Condición**: `tipo == "ordenes"` en el form de `POST /procesar`.
- **Resultado**: HTTP 422 con detalle `"Carga de Orden de Compra todavía no está
  implementada"`, antes de leer el archivo (`main.py:162-167`, comentario `# SC-25:
  fail-fast antes de cualquier I/O o invocación a Gemini`).
- **Prioridad**: Media.
- **Archivo**: `main.py:152-167`.
- **Observaciones**: [IMPLEMENTADO]. Confirmado por
  `tests/test_main_integration.py:445-460` (`test_tipo_ordenes_retorna_422_sin_llamar_robot`),
  que verifica explícitamente que `procesar_archivo`/`procesar_comparativa` no se llaman.

### RN-EXTRACCIONAPI-006 — Fail-fast de `proceso_comercial_id` inválido, antes de invocar Gemini

- **Descripción**: si el form incluye `licitacion_id` (parámetro; conceptualmente un
  `proceso_comercial_id`), se valida su existencia y pertenencia a la droguería de la
  instancia **antes** de guardar el archivo o llamar a `extraccion_ia`.
- **Condición**: `licitacion_id` no vacío en el form de `POST /procesar`.
- **Resultado**: `validar_proceso_comercial_id` (`procesos_comerciales_client.py:30-77`)
  lanza HTTP 422 si el UUID es inválido, si no existe, o si pertenece a otra droguería —
  sin distinguir estos dos últimos casos en el mensaje, para no filtrar existencia entre
  tenants (`procesos_comerciales_client.py:35-37`). El llamado ocurre antes de cualquier
  guardado de archivo (`main.py:174`, previo a la sección `GUARDAR ARCHIVO`).
- **Prioridad**: Alta.
- **Archivo**: `main.py:169-174`, `procesos_comerciales_client.py:30-77`.
- **Observaciones**: [IMPLEMENTADO]. Nota importante: el propio comentario de `main.py`
  (`:169-173`) aclara que la vinculación a un proceso comercial **no es obligatoria** en
  este endpoint — se resuelve más tarde, en la pantalla "Validar extracción"
  (`openspec/changes/validar-extraccion/proposal.md`). `licitacion_id` sigue aceptado y
  validado solo si viene seteado. Confirmado por
  `tests/test_main_integration.py:309-434` (SC-23/SC-24/SC-25).

### RN-EXTRACCIONAPI-007 — Anti-leak de tenant al resolver nombres de procesos comerciales

- **Descripción**: al listar documentos (`GET /api/documentos`), el nombre del proceso
  comercial vinculado se resuelve escopeado por `drogueria_id`; un `proceso_comercial_id`
  que no matchea esa droguería se trata igual que "sin vincular".
- **Condición**: cualquier `proceso_comercial_id` presente en `extraction_results` que no
  aparezca en el resultado de `listar_nombres_procesos_comerciales` (borrado, o de otra
  droguería).
- **Resultado**: cita literal (`procesos_comerciales_client.py:84-88`):

  > "El caller (GET /api/documentos) trata un id ausente en el dict igual que 'sin
  > vincular' — nunca debe mostrar el nombre real de un proceso de otra droguería."

  Implementado en `main.py:393-396`: `row["proceso_comercial"] = {...} if nombre else None`.
- **Prioridad**: Alta (seguridad/aislamiento multi-tenant).
- **Archivo**: `procesos_comerciales_client.py:80-115`, `main.py:388-397`.
- **Observaciones**: [IMPLEMENTADO]. Confirmado por
  `tests/test_main_integration.py:549-589`
  (`test_proceso_comercial_de_otra_drogueria_se_muestra_como_none`).

### RN-EXTRACCIONAPI-008 — Identificación de usuario opcional, nunca bloqueante

- **Descripción**: `POST /procesar` acepta pero no exige un JWT `Authorization: Bearer`.
  Sin header, la request funciona igual que antes (`subido_por=NULL`); con un header
  malformado, sí falla (401) — no se degrada en silencio.
- **Condición**: cualquier request a `/procesar` (única ruta que usa
  `get_usuario_id_actual` como `Depends`, `main.py:160`).
- **Resultado**: `get_bearer_token_opcional` (`auth.py:23-34`) retorna `None` sin header;
  levanta 401 si hay header pero no tiene forma `Bearer <token>`.
  `get_usuario_id_actual` (`auth.py:37-67`) retorna `None` si no hay token, levanta 401 si
  el token es inválido/vencido, y retorna `None` (con `warning` logueado) si el token es
  válido pero el `sub` no tiene fila en `usuarios` todavía.
- **Prioridad**: Media.
- **Archivo**: `auth.py:1-68`.
- **Observaciones**: [IMPLEMENTADO]. Motivo explícito en el docstring de módulo
  (`auth.py:1-11`): conviven el HTML viejo (sin ningún concepto de sesión, sin cuentas
  creadas) y el frontend nuevo (con login real); "Pasa a ser obligatoria recién cuando se
  retire el HTML viejo". Confirmado por `tests/test_extraccion_auth.py`.

### RN-EXTRACCIONAPI-009 — Formato-por-cliente (§8) inyectado al prompt, opcional y no bloqueante

- **Descripción**: si existen instrucciones cargadas para el `cliente_id` + `doc_type` de
  la request, se resuelven y pasan como `instrucciones_extra` al pipeline de
  `extraccion_ia`. Si la consulta falla o no hay match, se sigue sin instrucciones.
- **Condición**: cada request a `POST /procesar` con `cliente_id` no vacío.
- **Resultado**: `_resolver_formato_prompt` (`main.py:122-149`) consulta
  `cliente_formato_documentos` filtrando por `cliente_id`, `doc_type` y `activo=True`;
  ante cualquier excepción, loguea `warning` y retorna `(None, None)` — nunca bloquea la
  carga (`main.py:144-149`, comentario `# ambos None si no hay nada configurado o la
  consulta falla (nunca bloquea la carga del documento)`).
- **Prioridad**: Media.
- **Archivo**: `main.py:122-149,218-223`.
- **Observaciones**: [IMPLEMENTADO].

### RN-EXTRACCIONAPI-010 — Extensiones permitidas según tipo de documento

- **Descripción**: el set de extensiones válidas en `/procesar` depende de `tipo`.
- **Condición**: `tipo == "comparativas"` vs. cualquier otro valor.
- **Resultado**: comparativas admite `.pdf, .jpg, .jpeg, .png, .xls, .xlsx, .ods, .html,
  .htm`; el resto admite solo `.pdf, .jpg, .jpeg, .png, .xls, .xlsx` (`main.py:183-193`).
  Fuera de este set → HTTP 415.
- **Prioridad**: Media.
- **Archivo**: `main.py:183-193`.
- **Observaciones**: [IMPLEMENTADO].

### RN-EXTRACCIONAPI-011 — Limpieza garantizada del archivo temporal

- **Descripción**: el archivo guardado en disco durante `/procesar` (y su directorio
  temporal, si queda vacío) se elimina siempre, sin importar el resultado.
- **Condición**: cualquier finalización de `/procesar` (éxito o cualquier excepción
  capturada).
- **Resultado**: bloque `finally` (`main.py:339-353`) que borra `destino` si existe, y
  el `tmp_dir` si queda vacío tras el borrado — ambos envueltos en `try/except` con
  `logger.warning`/`logger.debug`, sin propagar el error de limpieza.
- **Prioridad**: Media.
- **Archivo**: `main.py:339-353`.
- **Observaciones**: [IMPLEMENTADO]. Nota: esto borra el archivo **subido** (el original),
  no el CSV generado por `extraccion_ia` — el CSV permanece en `OUTPUT_BASE`/
  `COMPARATIVAS_OUTPUT_BASE` como fuente de verdad (RN-EXTRACCIONAPI-003).

### RN-EXTRACCIONAPI-012 — Tipos de documento soportados por la persistencia

- **Descripción**: `persistir_output_final` solo acepta `doc_type` en
  `{"comparativa", "licitacion"}`; cualquier otro valor aborta el INSERT.
- **Condición**: cada llamada a `persistir_output_final`.
- **Resultado**: cita literal (`persistent_output.py:28-31`):

  > "Tipos de documento con pipeline de extraccion real hoy. 'orden_compra' todavia no
  > tiene extractor propio (ver presupuestacion/extraccion/) y 'cotizacion' es manejado
  > como 'licitacion' por el robot generico."

  Si `doc_type` no está en `_DOC_TYPES_SOPORTADOS`, se loguea `error` y se retorna `None`
  sin INSERT (`persistent_output.py:182-188`).
- **Prioridad**: Media.
- **Archivo**: `persistent_output.py:28-31,182-188`.
- **Observaciones**: [IMPLEMENTADO]. Confirmado por
  `tests/test_persistent_output.py:290-311`
  (`test_persistir_output_final_doc_type_invalido`). Nota: `crear_sesion`
  (`persistent_chunking.py`) sí acepta `"orden_compra"` como `doc_type` válido en su
  firma (`:42`), lo cual es consistente porque una sesión puede crearse antes de saberse
  que el `doc_type` no tiene pipeline (aunque en la práctica `tipo == "ordenes"` corta
  antes por RN-EXTRACCIONAPI-005, sin llegar a `crear_sesion`).
