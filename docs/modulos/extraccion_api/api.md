# API pública — API & Persistencia (legacy)

Funciones y endpoints públicos (no prefijados con `_`) de cada archivo, con su firma
real. Los `_helpers` privados se mencionan solo cuando son relevantes para entender el
flujo.

## `main.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `wants_json` | `(request: Request) -> bool` | Decide formato de respuesta de `/procesar` (`:80-83`). |
| `render_upload_response` | `(request, context: dict, status_code=200)` | Único punto de salida de `/procesar` (`:86-101`). |
| `home`, `licitaciones_page`, `upload_page`, `calendario_page`, `historial_page`, `guia_usuario` | `GET` handlers | Rutas HTML Jinja2 (`:107-119,356-363,484-486`). |
| `procesar` | `POST /procesar` | Pipeline completo, ver [`flujo.md`](./flujo.md) (`:152-353`). |
| `listar_documentos` | `GET /api/documentos` | `:366-397`. |
| `detalle_documento` | `GET /api/documentos/{doc_id}` | `:400-432`. |
| `descargar_documento_supabase` | `GET /api/documentos/{doc_id}/descargar` | `:435-481`. |
| `descargar` | `GET /descargar/{nombre_archivo}?origen=&modulo=` | `:489-498`. |

## `routers/licitaciones.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `validar_licitacion_id` | `async (licitacion_id: str \| None) -> str \| None` | Valida UUID contra tabla `licitaciones`; sin call site activo confirmado (`:45-75`). |
| `listar` | `GET /api/licitaciones` | Paginado, filtros `estado`/`tipo`/`q` (`:82-116`). |
| `listar_activas` | `GET /api/licitaciones/activas` | `:119-130`. |
| `calendario` | `GET /api/licitaciones/calendario` | `:133-187`. |
| `obtener` | `GET /api/licitaciones/{lic_id}` | `:190-221`. |
| `crear` | `POST /api/licitaciones` | `:224-236`. |
| `actualizar` | `PATCH /api/licitaciones/{lic_id}` | `:239-267`. |
| `eliminar` | `DELETE /api/licitaciones/{lic_id}` | Bloqueado con 409 si tiene archivos vinculados (`:270-308`). |

## `routers/extraction_results.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `actualizar` | `PATCH /api/extraction-results/{result_id}` | Vincula/desvincula `licitacion_id`, cambia `document_type` (`:32-60`). |

## `routers/clientes.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `listar_activos` | `GET /api/clientes -> list[ClienteActivo]` | Nunca falla, devuelve `[]` ante cualquier error (`:29-54`). |

## `schemas/licitaciones.py`

| Símbolo | Rol |
|---|---|
| `LicitacionBase`, `LicitacionCreate`, `LicitacionUpdate`, `LicitacionOut`, `LicitacionDetalle` | Modelos CRUD de `licitaciones`. |
| `ArchivoVinculado`, `ExtractionResultOut`, `ExtractionResultUpdate` | Modelos compartidos entre `licitaciones.py` y `extraction_results.py` (`ExtractionResultOut` hereda de `ArchivoVinculado`, `:126-129`). |
| `LicitacionActiva`, `LicitacionCalendario`, `LicitacionListResponse` | Vistas específicas (selector de upload, calendario, listado paginado). |
| `_normalize_count` | `(row: dict) -> dict` | Aplana `archivos_count:[{count:N}]` → `int` (`:18-25`), usado por 3 endpoints de `licitaciones.py`. |

## `supabase_client.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `get_client` | `() -> Client \| None` | Singleton, feature flag `ENABLE_RESULT_PERSISTENCE` (`:50-97`). |
| `is_enabled` | `() -> bool` | Guardia rápida (`:100-105`). |
| `resolver_drogueria_id_unica` | `(client: Client) -> str \| None` | Ver RN-EXTRACCIONAPI-002 (`:108-150`). |
| `reset_client_for_testing` | `() -> None` | Solo para tests (`:153-160`). |

## `persistent_output.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `calcular_sha256` | `(path: Path) -> str` | Hexdigest SHA256, lectura en bloques de 64KB (`:34-53`). |
| `buscar_duplicado_con_lock` | `async (*, source_sha256: str) -> UUID \| None` | RPC `reserve_extraction` (`:56-103`). |
| `persistir_output_final` | `async (*, session_id, doc_type, rows, csv_path, client_id, source_filename, source_sha256, licitacion_id=None) -> UUID \| None` | INSERT de metadata (`:106-244`). |

## `persistent_chunking.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `crear_sesion` | `async (*, doc_name, client_id, total_chunks, doc_type, formato_usado_id=None, subido_por=None) -> UUID \| None` | INSERT `processing_sessions` (`:24-91`). |
| `guardar_chunk` | `(*, session_id, chunk_num, resultado_json) -> bool` | Síncrona; UPSERT idempotente en `chunk_results` (`:94-149`). |
| `cargar_chunks_existentes` | `(*, session_id) -> dict[int, dict]` | Síncrona; para reanudación (`:152-194`). |
| `cerrar_sesion` | `async (*, session_id, status, error_msg=None) -> None` | UPDATE `processing_sessions` (`:197-237`). |

## `background_tasks.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `schedule_persist_output` | `async (bg: BackgroundTasks, *, session_id, doc_type, rows, csv_path, client_id, source_filename, source_sha256, licitacion_id=None) -> None` | Registra `_retry_persist` como `BackgroundTask` (`:153-196`). |
| `_retry_persist` | `async (*, ..., attempt=0, max_attempts=3) -> None` | Recursiva, con backoff (`:39-150`) — privada pero documentada por su centralidad en el flujo. |

## `auth.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `get_bearer_token_opcional` | `(authorization: str \| None = Header(None)) -> str \| None` | `:23-34`. |
| `get_usuario_id_actual` | `(token: str \| None = Depends(...)) -> str \| None` | `:37-67`, delega en `services.shared.auth_jwt.verificar_token` (documentado en [`../core/`](../core/README.md)). |

## `procesos_comerciales_client.py`

| Símbolo | Firma | Rol |
|---|---|---|
| `validar_proceso_comercial_id` | `async (proceso_comercial_id: str \| None) -> str \| None` | Ver RN-EXTRACCIONAPI-006 (`:30-77`). |
| `listar_nombres_procesos_comerciales` | `async (ids: list[str]) -> dict[str, str]` | Ver RN-EXTRACCIONAPI-007 (`:80-115`). |

Ver [`../procesos_comerciales/api.md`](../procesos_comerciales/api.md) para el resto de
la API de ese módulo, dueño de la tabla que este cliente consulta.
