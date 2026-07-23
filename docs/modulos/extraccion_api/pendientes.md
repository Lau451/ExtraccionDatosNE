# Pendientes — Auditoría técnica de API & Persistencia (legacy)

Clasificación P1 (ausencia de una capacidad esperada / riesgo estructural) / P2 (deuda
técnica relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión.

## P1 — Riesgo estructural

1. **`processing_sessions` puede quedar en `status="running"` para siempre si el robot
   falla después de crear la sesión.** `crear_sesion` inserta la fila (`main.py:228-235`)
   **antes** de invocar `procesar_archivo`/`procesar_comparativa` (`main.py:241-256`). Si
   esa llamada lanza cualquiera de las excepciones capturadas en
   `main.py:283-337` (`UnsupportedFormatError`, `ParserError`,
   `NoProvidersDetectedError`, `GeminiQuotaExceededError`, `GeminiRateLimitError`,
   `GeminiAPIError`, `Exception` genérica), ninguna de esas ramas llama a `cerrar_sesion`
   — `schedule_persist_output` (único caller de `cerrar_sesion` en este módulo, vía
   `_retry_persist`) nunca se invoca en esos caminos. [IMPLEMENTADO], confirmado por
   lectura completa de `main.py:152-353` y grep de `cerrar_sesion(` en todo el
   repositorio en esta sesión (únicos 2 call sites reales: `background_tasks.py:96,118`).
   La sesión queda huérfana en `"running"`, sin `completed_at` ni `error_msg`. Ver
   [`estados.md`](./estados.md).

2. **Fallback no determinístico de `resolver_drogueria_id_unica` sin mitigación en
   código, cacheado para toda la vida del proceso.** Ver D-EXTRACCIONAPI-003 en
   [`decisiones.md`](./decisiones.md) y RN-EXTRACCIONAPI-002 en
   [`reglas.md`](./reglas.md). [IMPLEMENTADO], riesgo documentado por el propio autor en
   `supabase_client.py:116-124`, sin ningún test que ejercite el caso de más de una fila
   en `droguerias` (los tests confirmados en `tests/test_supabase_client.py:178-235`
   siempre mockean exactamente una fila de retorno). Configurar `DROGUERIA_ID` en cada
   ambiente elimina el riesgo por completo — es una acción operativa, no de código, pero
   el código no fuerza ni valida que se haya hecho.

3. **Estado incierto de la tabla legacy `licitaciones`, no verificable desde código.**
   `procesos_comerciales_client.py:7-11` afirma que la tabla "ya no existe", pero
   `routers/licitaciones.py` sigue consultándola activamente en 7 endpoints, y el HTML
   legacy (`static/licitaciones.js`, `calendario.js`) sigue llamando a esas rutas en
   producción, según `ROADMAP.md:94-117`. Mismo hallazgo ya documentado desde el otro
   lado en [`../procesos_comerciales/pendientes.md`](../procesos_comerciales/pendientes.md)
   P3 — se eleva a P1 en este módulo porque acá el código activo que depende de la
   respuesta (7 endpoints de un router completo, no solo un docstring) es mayor.
   **Pendiente de definición funcional**: no es verificable desde código si la tabla
   existe físicamente en la base de datos real, está vacía, o efectivamente fue
   eliminada (en cuyo caso las 7 queries de `routers/licitaciones.py` estarían fallando
   en producción con cada invocación, silenciosamente para el usuario final del HTML
   legacy si no hay monitoreo de esos errores 500).

## P2 — Deuda técnica relevante

1. **Docstring del backoff exponencial no coincide con el comportamiento real
   verificado por el propio test del proyecto.** `background_tasks.py:5-6` describe
   "Backoff exponencial: 2^n segundos (2s, 4s, 8s entre intentos)", pero con
   `_MAX_ATTEMPTS=3` (`background_tasks.py:36`) solo hay 2 esperas reales (2s y 4s) antes
   del intento final — nunca se llega a esperar 8s, porque el tercer fallo agota los
   intentos inmediatamente. [IMPLEMENTADO], confirmado exactamente por
   `tests/test_background_tasks.py:124-150`
   (`test_retry_persist_backoff_exponencial`, `assert sleep_args == [2, 4]`). El
   docstring parece describir un esquema de 4 intentos (3 esperas) en vez de los 3
   intentos reales (2 esperas) — desalineado con el propio código que documenta.

2. **Firma de `persistir_output_final`/`crear_sesion` con parámetros que mienten sobre
   su efecto.** `session_id` y `client_id` se aceptan pero nunca se persisten,
   documentado solo en el docstring (`persistent_output.py:134-138`), no en la firma en
   sí (sin ningún marcador de tipo o nombre que indique "solo compatibilidad"). Ver
   D-EXTRACCIONAPI-005. [IMPLEMENTADO]. Riesgo de que un futuro cambio en el schema
   restaure esas columnas y alguien asuma (incorrectamente) que ya se están usando desde
   este código.

3. **Endpoints `GET /api/documentos/{doc_id}` y `GET /api/documentos/{doc_id}/descargar`
   sin consumidor confirmado en el frontend nuevo.** Ninguno de los dos apareció en el
   grep de esta sesión contra `frontend/src/lib/api/extraccion.ts` (el único archivo de
   API de extracción del frontend nuevo encontrado). Ambos leen de
   `comparativas_results`/`licitaciones_results` — tablas que ningún archivo de este
   módulo escribe (ver [`base_de_datos.md`](./base_de_datos.md)); su productor real
   queda **fuera de alcance** de esta sesión. No se puede confirmar si estos 2 endpoints
   siguen en uso (por el HTML legacy, vía JS no auditado exhaustivamente en esta sesión)
   o son código muerto.

4. **`"partial"` es un estado declarado en `cerrar_sesion` pero sin ningún productor.**
   Ver [`estados.md`](./estados.md). [IMPLEMENTADO], confirmado por grep exhaustivo de
   `cerrar_sesion(` en todo el repositorio. Puede ser vocabulario reservado para un flujo
   futuro (o de `extraccion_ia`, no verificado en detalle en esta sesión) — sin uso
   actual, es superficie muerta en la firma de la función.

## P3 — Menor

1. **Dos validadores de UUID en paralelo sin unificar.** Ver D-EXTRACCIONAPI-002 y la
   tabla comparativa en [`arquitectura.md`](./arquitectura.md). Riesgo bajo mientras el
   comentario en `procesos_comerciales_client.py:9-11` siga siendo la única fuente de
   verdad sobre cuál usar para cada caso — pero no hay ningún mecanismo de código
   (deprecation warning, comentario en `routers/licitaciones.py` mismo) que evite que un
   desarrollador nuevo reintroduzca `validar_licitacion_id` en un flujo nuevo por error.

2. **`GET /api/documentos/{doc_id}` y `GET /api/documentos/{doc_id}/descargar` duplican
   casi exactamente la misma lógica de `_query`** (resolver `meta`, elegir tabla según
   `document_type`, leer `rows`) — `main.py:406-426` y `main.py:441-461` — sin una función
   compartida. Cosmético, no afecta corrección.

3. **Sin test de integración que cubra el gap P1-1** (sesión huérfana en `"running"`
   cuando el robot falla). Todos los tests de `tests/test_main_integration.py` que
   simulan fallos del robot (`TestProcesarFileGeminiFailsChunk1`) verifican solo el
   status code HTTP, no el estado final de `processing_sessions` — el propio comentario
   del test lo reconoce: "no verificamos BD aquí, solo el HTTP response del endpoint"
   (`tests/test_main_integration.py:198-199`).
