# Decisiones de diseño — API & Persistencia (legacy)

Numeración D-EXTRACCIONAPI-NNN, verificada contra el código en esta sesión.

### D-EXTRACCIONAPI-001 — Servir HTML y JSON desde el mismo endpoint `/procesar`

- **Decisión**: `render_upload_response` decide el formato de la respuesta
  (`JSONResponse` vs. `templates/index.html` renderizado) en función de headers HTTP
  (`Accept`, `X-Requested-With`), en vez de tener dos rutas separadas o una API JSON pura
  con el HTML consumiéndola por `fetch`.
- **Motivo**: [SUPOSICIÓN], no hay comentario explícito que declare por qué se eligió
  este patrón. Inferido del contexto documentado en `auth.py:1-11` y
  `ROADMAP.md:74-92`: conviven dos frontends del mismo backend en el mismo momento —
  el HTML legacy (`templates/index.html`, submit de formulario nativo, espera HTML de
  vuelta) y el frontend nuevo (`frontend/src/lib/api/extraccion.ts:42-58`, hace `fetch`,
  espera JSON) — apuntando al mismo endpoint `/procesar` durante la transición. Separar
  en dos rutas hubiera requerido duplicar toda la lógica de validación/procesamiento/
  persistencia entre ambas, o factorizarla en una función compartida; la decisión tomada
  evita esa duplicación al costo de una función con dos formatos de salida.
- **Ventajas**: un solo punto de mantenimiento para toda la lógica de negocio de
  `/procesar` (deduplicación, validación de proceso comercial, invocación de
  `extraccion_ia`, persistencia) mientras ambos frontends coexisten.
- **Desventajas**: `render_upload_response` y cada rama de `except` de `procesar` deben
  mantener consistencia entre el `status_code` HTTP y el contenido de `context` para
  ambos formatos; un cambio en un campo de la respuesta JSON puede pasar desapercibido en
  el camino HTML o viceversa, sin ningún tipo compartido que los ate en tiempo de
  compilación (Python + Jinja2, sin `response_model`).

### D-EXTRACCIONAPI-002 — Mantener `routers/licitaciones.py` intacto, con un validador de UUID paralelo sin uso activo

- **Decisión**: no eliminar ni refactorizar `validar_licitacion_id`
  (`routers/licitaciones.py:45-75`) ni el resto del router, a pesar de que `/procesar`
  usa exclusivamente `validar_proceso_comercial_id` (`procesos_comerciales_client.py`)
  desde el cambio `carga-documentos`.
- **Motivo**: [IMPLEMENTADO], explícito en dos fuentes: el propio docstring de
  `procesos_comerciales_client.py:9-11` ("ese módulo se deja intacto mientras el HTML
  legacy... lo siga usando") y `ROADMAP.md:94-117`, que documenta que
  `templates/licitaciones.html`/`calendario.html` y sus scripts (`static/licitaciones.js`,
  `calendario.js`) siguen llamando activamente a `/api/licitaciones/*` — retirar el
  router ahora rompería esas 2 páginas del HTML legacy en producción.
- **Ventajas**: cero riesgo de romper las páginas legacy en producción mientras siguen
  activas; el cambio de flujo nuevo (`procesos_comerciales_client.py`) se hizo aislado,
  sin tocar código compartido.
- **Desventajas**: dos validadores de UUID con la misma forma (`main.py`/
  `arquitectura.md`, tabla comparativa) coexisten en el mismo módulo apuntando a tablas
  distintas, uno de los cuales (`validar_licitacion_id`) puede estar consultando una
  tabla cuyo estado real en la base de datos es incierto (ver
  [`pendientes.md`](./pendientes.md) P1) — cualquier desarrollador nuevo puede
  confundirse sobre cuál usar para un caso nuevo.

### D-EXTRACCIONAPI-003 — Fallback no determinístico para `drogueria_id` en vez de fallar duro

- **Decisión**: cuando `DROGUERIA_ID` no está seteada, `resolver_drogueria_id_unica`
  hace `SELECT id FROM droguerias LIMIT 1` (sin `ORDER BY`) en vez de retornar `None`/
  lanzar una excepción directamente.
- **Motivo**: [IMPLEMENTADO], explícito en el propio docstring
  (`supabase_client.py:116-124`): "válido HOY porque esta base tiene una sola droguería" —
  la decisión prioriza no romper el flujo actual (una sola droguería en producción hoy)
  sobre exigir configuración explícita desde el primer día.
- **Ventajas**: cero fricción operativa mientras la base sirve una sola droguería —no
  hace falta setear `DROGUERIA_ID` en ningún ambiente hoy para que el sistema funcione.
- **Desventajas**: el propio autor documenta el riesgo sin mitigarlo en código —
  "Postgres puede devolver cualquiera de las dos de forma no determinística" apenas haya
  una segunda droguería, y el resultado incorrecto se **cachea para toda la vida del
  proceso** (`_drogueria_id_cache`, `supabase_client.py:42`), por lo que un arranque con
  mala suerte en el orden de filas queda fijo hasta el próximo restart. El schema de
  `presupuestacion/` es explícitamente multi-tenant, así que el escenario de riesgo no es
  hipotético (`supabase_client.py:121-124`). Ver P1 en
  [`pendientes.md`](./pendientes.md).

### D-EXTRACCIONAPI-004 — Persistencia final como `BackgroundTask` con retry, no bloqueante

- **Decisión**: `persistir_output_final` corre después de responder al cliente HTTP
  (`FastAPI BackgroundTasks`), con hasta 3 intentos y backoff exponencial, en vez de
  persistir de forma síncrona antes de responder.
- **Motivo**: [IMPLEMENTADO], explícito en el docstring de `background_tasks.py:1-20`: la
  tarea "se ejecuta DESPUÉS de que FastAPI envia la respuesta HTTP al cliente, por lo que
  NO bloquea la descarga del CSV" — el CSV en disco (fuente de verdad, ver
  RN-EXTRACCIONAPI-003) ya está disponible independientemente de si Supabase responde a
  tiempo o falla.
- **Ventajas**: la latencia percibida por el usuario no incluye la escritura en Supabase;
  un fallo transitorio de Supabase (hasta 3 intentos con 2s/4s de espera) no afecta la
  entrega del resultado al usuario.
- **Desventajas**: si los 3 intentos fallan, el único rastro persistente del intento (más
  allá del log de aplicación) es la fila `processing_sessions` con `status="failed"` — y
  solo si `session_id` no era `None`. No hay ninguna cola de reintento posterior ni
  alerta automática más allá del log `ERROR`; la reconciliación es manual, como el propio
  comentario del código indica ("session_id=%s sha256=%s ... para reconciliacion
  manual", `background_tasks.py:107-116`).

### D-EXTRACCIONAPI-005 — `session_id`/`client_id` aceptados por compatibilidad pero no persistidos

- **Decisión**: `persistir_output_final` y `crear_sesion` siguen recibiendo `client_id`
  (ambas) y `session_id` (la primera) como parámetros, pero ninguno se escribe en las
  columnas reales de `extraction_results`/`processing_sessions` del schema nuevo.
- **Motivo**: [IMPLEMENTADO], explícito en el docstring de
  `persistent_output.py:134-138`: esas columnas "no existen como columnas usables en el
  extraction_results del schema nuevo" — cambiar la firma de las funciones hubiera
  obligado a tocar todos los callers (`main.py`, `background_tasks.py`) para un campo que
  de todas formas no se usa.
- **Ventajas**: no rompe la firma de funciones ya integradas en `main.py` y
  `background_tasks.py`; el cambio de schema se absorbe dentro de la función de
  persistencia sin propagarse hacia arriba.
- **Desventajas**: la firma de ambas funciones miente sobre lo que realmente hacen con
  esos parámetros — alguien que lea solo la firma (sin el docstring) puede asumir que se
  persisten. `licitacion_id` sí se persiste (como `proceso_comercial_id`), lo cual hace
  la inconsistencia más notable: 3 parámetros de compatibilidad con tratamiento distinto
  entre sí (`session_id`/`client_id` descartados, `licitacion_id` sí escrito) en la misma
  firma de función.

### D-EXTRACCIONAPI-006 — Identificación de usuario opcional en vez de obligatoria

Ver RN-EXTRACCIONAPI-008 para el detalle de comportamiento. Documentado también como
decisión porque implica una superficie de ataque deliberadamente abierta: cualquier
caller anónimo puede invocar `/procesar` sin JWT, exactamente igual que hoy. El motivo
está documentado explícitamente (`auth.py:1-11`, `ROADMAP.md:74-92`): exigir login ahora
obligaría a enseñarle un flujo de autenticación a usuarios del HTML legacy que va a
descontinuarse, para repetir el mismo onboarding después en el sistema que lo reemplaza —
la decisión pospone el costo de UX hasta que valga la pena pagarlo una sola vez.
