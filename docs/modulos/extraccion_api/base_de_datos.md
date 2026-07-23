# Base de datos — API & Persistencia (legacy)

Todas las tablas se consultan vía `supabase-py` con el cliente `service_role`
(`supabase_client.py:get_client`, bypasea RLS). No se encontró en este módulo ningún uso
de `user_client`/RLS-aware client (ese patrón es propio de `presupuestacion/core/`, ver
[`../core/base_de_datos.md`](../core/base_de_datos.md)).

## `extraction_results` (schema nuevo de `presupuestacion/`)

Metadata de cada documento extraído — **nunca** las filas de datos (ver
RN-EXTRACCIONAPI-003).

| Columna | Origen/uso en este módulo |
|---|---|
| `id` | PK, generada por Supabase; retornada por `persistir_output_final` (`persistent_output.py:228`). |
| `drogueria_id` | Resuelta por `resolver_drogueria_id_unica` (`persistent_output.py:190,201`). |
| `document_type` | `"comparativa"` \| `"licitacion"` — validado contra `_DOC_TYPES_SOPORTADOS` antes del INSERT (`persistent_output.py:31,182-188`). |
| `source_filename` | Nombre original del archivo subido (`persistent_output.py:203`). |
| `source_sha256` | Hash SHA256, usado para deduplicación futura (`persistent_output.py:204`). |
| `row_count` | `len(rows)` (`persistent_output.py:205`). |
| `csv_disk_path` | Path absoluto del CSV en disco — fuente de verdad de las filas (`persistent_output.py:206`). |
| `status` | Siempre `"completed"` en el INSERT de este módulo (`persistent_output.py:207`); la RPC `reserve_extraction` referencia también `"partial"`/`"failed"` como valores posibles del lado de la base (`persistent_output.py:69`, docstring), pero ningún código de este módulo los escribe. |
| `proceso_comercial_id` | Solo si `licitacion_id` (parámetro, ya validado) no es `None` (`persistent_output.py:209-210`). Antes de la corrección documentada en el propio código, se aceptaba el parámetro y se descartaba sin persistirlo (`tests/test_licitaciones_persistence.py:1-8`). |
| `licitacion_id` | Columna leída (no escrita) por `routers/extraction_results.py` (`_SELECT_FIELDS`, `:16-19`) y `routers/licitaciones.py` (`obtener`, filtro `.eq("licitacion_id", ...)`, `:208`) — **nombre distinto** de `proceso_comercial_id`; no hay evidencia en este módulo de que sean la misma columna física o de que coexistan ambas. Pendiente de definición funcional (ver [`pendientes.md`](./pendientes.md)). |

**Operaciones**:
- `INSERT` — `persistir_output_final` (`persistent_output.py:212-219`).
- `SELECT` — `GET /api/documentos` (`main.py:372-383`), `GET /api/documentos/{doc_id}` (`main.py:407-413`), `GET /api/documentos/{doc_id}/descargar` (`main.py:442-448`), `routers/extraction_results.py:actualizar` (re-select tras update, `:48-54`), `routers/licitaciones.py:calendario` (`:152-158`), `:obtener` (archivos vinculados, `:202-211`), `:eliminar` (conteo de archivos vinculados, `:275-281`).
- `UPDATE` — `routers/extraction_results.py:actualizar` (`:40-45`), único `UPDATE` de esta tabla en el módulo.
- `RPC` — `reserve_extraction` (`persistent_output.py:79`), función server-side no visible desde este repositorio; hace `SELECT FOR UPDATE` por `source_sha256` (ver RN-EXTRACCIONAPI-001).

## `processing_sessions` (schema nuevo de `presupuestacion/`)

Ciclo de vida de una sesión de procesamiento chunked, 1 por request a `/procesar`.

| Columna | Origen/uso |
|---|---|
| `id` | PK, retornada por `crear_sesion` (`persistent_chunking.py:75`). |
| `drogueria_id` | Resuelta por `resolver_drogueria_id_unica` (`persistent_chunking.py:55,61`). |
| `doc_name` | Nombre del documento original (`persistent_chunking.py:62`). |
| `doc_type` | `"comparativa"` \| `"licitacion"` \| `"orden_compra"` (`persistent_chunking.py:42,63`). |
| `total_chunks` | Estimado, puede ser `0` como placeholder (`main.py:231`, `persistent_chunking.py:64`). |
| `status` | `"running"` al crear (`persistent_chunking.py:65`); `"completed"`/`"failed"` al cerrar desde `background_tasks.py` (`:96,:118-122`); `"partial"` documentado como valor válido (`persistent_chunking.py:208`) pero sin ningún call site que lo escriba, confirmado por grep en esta sesión. Ver [`estados.md`](./estados.md). |
| `formato_usado_id` | FK a `cliente_formato_documentos`, si se resolvió uno (`persistent_chunking.py:66`, §8). |
| `subido_por` | `usuario_id` del JWT verificado, o `None` (`persistent_chunking.py:67`). |
| `completed_at` | Seteado por `cerrar_sesion` (`persistent_chunking.py:217`). |
| `error_msg` | Seteado por `cerrar_sesion` solo si `status != "completed"` (`persistent_chunking.py:219-220`). |

**Operaciones**: `INSERT` (`crear_sesion`, `persistent_chunking.py:71-73`), `UPDATE`
(`cerrar_sesion`, `:224-229`). No hay `SELECT` de esta tabla en ningún archivo de este
módulo (el único consumidor de lectura sería `extraccion_ia`, fuera de alcance).

## `chunk_results` (schema nuevo de `presupuestacion/`)

| Columna | Origen/uso |
|---|---|
| `drogueria_id` | Resuelta por `resolver_drogueria_id_unica` (`persistent_chunking.py:119,125`). |
| `session_id` | FK a `processing_sessions` (`persistent_chunking.py:126`). |
| `chunk_number` | Base 0 o 1 según el caller (`persistent_chunking.py:127`). |
| `resultado` | JSON con los datos extraídos del chunk (`persistent_chunking.py:128`). |
| `status` | Siempre `"completed"` (`persistent_chunking.py:129`) — sin otros valores observados. |

**Operaciones**: `UPSERT` con `ON CONFLICT(session_id, chunk_number)` (`guardar_chunk`,
`persistent_chunking.py:134-137`, idempotente); `SELECT` filtrado por `session_id` y
`status="completed"` (`cargar_chunks_existentes`, `:171-177`, usado para reanudación).

## `comparativas_results` / `licitaciones_results` (schema nuevo de `presupuestacion/`)

Leídas exclusivamente por `main.py`, en dos endpoints que sí devuelven las filas de
datos extraídos (a diferencia de `extraction_results`, que solo guarda metadata — ver
RN-EXTRACCIONAPI-003). Ninguna función de `persistent_output.py`/`persistent_chunking.py`
de este módulo escribe en estas dos tablas — no se encontró el `INSERT` correspondiente
en ningún archivo de los 12 listados en este módulo; su escritura queda **fuera de
alcance** de esta documentación (posiblemente en `presupuestacion/extraccion/`, no
verificado en esta sesión).

| Columna | Uso |
|---|---|
| `rows` | Único campo leído, filtrado por `extraction_id` (`main.py:417-425`, `:452-460`). |

**Operaciones**: `SELECT rows WHERE extraction_id = {doc_id} LIMIT 1`, elegida entre
`comparativas_results` (si `document_type == "comparativa"`) o `licitaciones_results`
(cualquier otro valor) — `GET /api/documentos/{doc_id}` (`main.py:406-426`),
`GET /api/documentos/{doc_id}/descargar` (`main.py:441-461`).

## `licitaciones` (tabla legacy)

Ver la tensión documentada en [`arquitectura.md`](./arquitectura.md) sobre si esta tabla
sigue existiendo en la base real.

| Columna | Uso |
|---|---|
| `id, nombre, tipo, apertura, vencimiento, tipo_gestion, modalidad, estado, monto_estimado, notas, comparativa_estado, created_at, updated_at` | `_SELECT_FIELDS` (`routers/licitaciones.py:28-32`), más `archivos_count:extraction_results(count)` (embed calculado). |

**Operaciones** (todas en `routers/licitaciones.py`): `SELECT` (`listar`, `:96-107`;
`listar_activas`, `:124-129`; `calendario`, `:143-146`; `obtener`, `:196-201`), `INSERT`
(`crear`, `:230`), `UPDATE` (`actualizar`, `:248-251`), `DELETE` (`eliminar`, `:286-289`,
bloqueado con 409 si tiene `extraction_results` vinculados).

## `clientes` (schema de `presupuestacion/`)

Lectura únicamente. `id, nombre` filtrados por `drogueria_id` y `activo=True`
(`routers/clientes.py:44-49`). Consumido por el selector de cliente del formulario de
upload.

## `cliente_formato_documentos` (schema de `presupuestacion/`)

Lectura únicamente, dentro de `main.py:_resolver_formato_prompt` (`:122-149`):
`id, instrucciones_prompt` filtrados por `cliente_id`, `doc_type` y `activo=True`
(`main.py:133-138`). Nunca bloquea la carga si falla (`try/except` con `logger.warning`,
`main.py:144-147`).

## `usuarios` (schema de `presupuestacion/`, dueño: módulo `usuarios/`)

Lectura únicamente, en `auth.py:get_usuario_id_actual` (`:58`): verifica que el `sub` del
JWT tenga fila en `usuarios` antes de atribuir la sesión; si no la tiene, continúa sin
atribución (`auth.py:59-65`). Este módulo no es dueño de esta tabla — mismo criterio que
`core/auth.py` en `presupuestacion/` (ver [`../core/README.md`](../core/README.md)).

## `droguerias` (schema de `presupuestacion/`)

Lectura únicamente, en `supabase_client.py:resolver_drogueria_id_unica` (`:143`):
`SELECT id LIMIT 1` sin filtro ni `ORDER BY`, solo si `DROGUERIA_ID` no está seteada. Ver
RN-EXTRACCIONAPI-002.

## `procesos_comerciales` (schema de `presupuestacion/`, dueño: módulo `procesos_comerciales`)

Lectura únicamente, siempre escopeada por `drogueria_id`, vía
`procesos_comerciales_client.py`:
- `validar_proceso_comercial_id` (`:64-70`): `SELECT id` filtrado por `id` y
  `drogueria_id`.
- `listar_nombres_procesos_comerciales` (`:102-107`): `SELECT id, nombre` filtrado por
  `id IN (...)` y `drogueria_id`.

Ver [`../procesos_comerciales/base_de_datos.md`](../procesos_comerciales/base_de_datos.md)
para el modelo completo de esta tabla desde el lado dueño.
