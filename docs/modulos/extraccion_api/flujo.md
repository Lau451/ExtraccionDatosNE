# Flujo — API & Persistencia (legacy)

## Flujo 1: `POST /procesar` end-to-end

```
Cliente (HTML legacy o frontend nuevo)
   │  multipart/form-data: archivo, tipo, licitacion_id?, cliente_id?
   │  Authorization: Bearer <jwt>?  (opcional)
   ▼
1. get_usuario_id_actual (Depends)              — auth.py:37-67
   └─ 401 si JWT malformado/inválido; None si no hay header o sin perfil
2. tipo == "ordenes"? → 422 fail-fast            — main.py:162-167 (RN-EXTRACCIONAPI-005)
3. validar_proceso_comercial_id(licitacion_id)   — procesos_comerciales_client.py:30-77
   └─ 422 si UUID inválido / no existe / otra droguería (RN-EXTRACCIONAPI-006)
4. Resolver origen_id (obtener_cliente, de extraccion_ia) + extensión
5. extensión permitida para `tipo`? → 415 si no  — main.py:183-193 (RN-EXTRACCIONAPI-010)
6. Guardar archivo en tmp_dir (asyncio.to_thread) — main.py:196-201
7. calcular_sha256(archivo)                       — persistent_output.py:34-53
8. buscar_duplicado_con_lock(sha256)              — persistent_output.py:56-103 (RPC reserve_extraction)
   └─ 409 si ya existe extraction_result completado con ese hash (RN-EXTRACCIONAPI-001)
9. _resolver_formato_prompt(cliente_id, doc_type) — main.py:122-149 (§8, opcional)
10. crear_sesion(...)                             — persistent_chunking.py:24-91
    └─ INSERT processing_sessions, status="running"
11. asyncio.Semaphore(15): procesar_archivo/procesar_comparativa (extraccion_ia)
    └─ asyncio.to_thread — main.py:241-256
    └─ [excepción] → salta a manejo de errores (paso 13)
12. Leer CSV generado → rows (csv.DictReader)      — main.py:260-267
13. schedule_persist_output(...)                   — background_tasks.py:153-196
    └─ bg.add_task(_retry_persist, ...) — se ejecuta DESPUÉS de responder al cliente
14. render_upload_response(request, {"tipo": tipo}) — 200 OK (HTML o JSON según headers)
    └─ finally: borrar archivo temporal + tmp_dir  — main.py:339-353 (RN-EXTRACCIONAPI-011)

[Manejo de errores — cualquier excepción en el paso 11, cada una con su propio status]:
  UnsupportedFormatError  → 415  (main.py:283-289)
  ParserError              → 422  (main.py:291-297)
  NoProvidersDetectedError → 422  (main.py:299-305)
  GeminiQuotaExceededError → 503  (main.py:307-313)
  GeminiRateLimitError     → 429  (main.py:315-321)
  GeminiAPIError            → 500  (main.py:323-329)
  Exception (genérica)      → 500  (main.py:331-337)

  En NINGUNA de estas ramas se llama a cerrar_sesion ni a schedule_persist_output —
  si crear_sesion (paso 10) ya insertó una fila, esa processing_sessions queda con
  status="running" indefinidamente. Ver estados.md y pendientes.md P1.
```

## Flujo 2: persistencia en background (post-respuesta)

Se ejecuta como `BackgroundTask` de FastAPI, después de que la respuesta HTTP del paso 14
del Flujo 1 ya fue enviada al cliente — no bloquea la descarga del CSV.

```
_retry_persist(attempt=0, max_attempts=3)         — background_tasks.py:39-150
   │
   ├─ persistir_output_final(...)  (timeout=60s, asyncio.wait_for)
   │    │
   │    ├─ rows vacío? → log error, retorna None    (persistent_output.py:163-170)
   │    ├─ rows > 50_000? → log warning, continúa    (persistent_output.py:172-179)
   │    ├─ doc_type no soportado? → log error, None  (persistent_output.py:182-188)
   │    ├─ resolver_drogueria_id_unica → None? → log error, retorna None
   │    └─ INSERT extraction_results (solo metadata) → UUID | None
   │
   ├─ éxito (UUID != None):
   │    └─ cerrar_sesion(session_id, status="completed")  — background_tasks.py:95-97
   │    └─ FIN
   │
   └─ excepción (o None sin excepción → RuntimeError sintético):
        ├─ intento agotado (siguiente_intento >= 3)?
        │    └─ log ERROR final (con session_id/sha256/filename)
        │    └─ cerrar_sesion(session_id, status="failed", error_msg=str(exc))
        │    └─ FIN — el CSV en disco sigue disponible, NUNCA se propaga la excepción
        │
        └─ no agotado:
             └─ sleep(2**siguiente_intento)  → 2s (intento 1) | 4s (intento 2)
             └─ recursión: _retry_persist(attempt=siguiente_intento)
```

Ver RN-EXTRACCIONAPI-004 para el detalle exacto del backoff (2 esperas, no 3).

## Flujo 3: `GET /api/documentos` — resolución de nombre de proceso comercial

```
GET /api/documentos?tipo=?
   │
   ├─ get_client() → None? → {"documentos": [], "sin_persistencia": true}
   │
   ├─ SELECT extraction_results (id, source_filename, document_type, row_count,
   │         status, created_at, proceso_comercial_id) ORDER BY created_at DESC
   │         [+ filtro document_type si tipo es "comparativa"/"licitacion"]
   │
   ├─ Extraer set de proceso_comercial_id no nulos
   ├─ listar_nombres_procesos_comerciales(ids)     — procesos_comerciales_client.py:80-115
   │    └─ SELECT id, nombre FROM procesos_comerciales
   │         WHERE id IN (...) AND drogueria_id = <esta instancia>
   │    └─ ids ausentes en el resultado (otra droguería / borrados) se omiten
   │
   └─ Por cada doc: proceso_comercial = {id, nombre} si hay match, si no None
        (RN-EXTRACCIONAPI-007 — nunca se filtra el nombre de otro tenant)
```

## Llamadas confirmadas hacia `extraccion_ia` (para contexto, no documentadas acá)

Confirmado por grep en esta sesión — el único caller de estas funciones en todo el
módulo es `main.py`:

- `obtener_cliente` (`robot.py`) — `main.py:180`, deriva `origen_id` del nombre de
  archivo.
- `procesar_archivo` (`robot.py`) — `main.py:250-254`, dentro de
  `asyncio.to_thread`.
- `procesar_comparativa` (`robot_comparativas.py`) — `main.py:243-247`, dentro de
  `asyncio.to_thread`.
- `parse_document`, `ParserError`, `UnsupportedFormatError` (`parsers.py`) — importados
  en `main.py:28` solo para capturar las excepciones tipadas que `procesar_archivo`/
  `procesar_comparativa` pueden propagar (no se invoca `parse_document` directamente
  desde este módulo).
- `get_output_dir`, `get_tmp_dir`, `OUTPUT_BASE`, `COMPARATIVAS_OUTPUT_BASE`
  (`config.py`) — usados para resolver rutas de disco (`main.py:195-197,491-496`).
- `GeminiQuotaExceededError`, `GeminiRateLimitError`, `GeminiAPIError`
  (`gemini_errors.py`) — capturadas en el manejo de errores de `/procesar`
  (`main.py:307-329`).
