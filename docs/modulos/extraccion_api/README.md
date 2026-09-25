# Módulo API & Persistencia (legacy) — `services/extraccion/{main.py,routers/,schemas/,supabase_client.py,persistent_output.py,persistent_chunking.py,background_tasks.py,auth.py,procesos_comerciales_client.py}`

## Qué es

API & Persistencia es la capa HTTP y de persistencia en Supabase del backend
`services/extraccion/` (Droguería Nueva Era). Es el módulo que recibe el archivo subido
por el usuario, lo guarda en disco, deduplica por hash, delega la extracción de datos en
el módulo [`extraccion_ia`](../extraccion_ia/) (`robot.py`/`robot_comparativas.py`/
`parsers.py`), lee el CSV resultante y persiste su metadata en Supabase — además de
exponer los endpoints CRUD de clientes y extraction results que consume el frontend
(Vite/React).

**T2 (2026-09-25, `odd/tasks/extraccion-multi-tenant.md`)** retiró el HTML legacy
(`templates/`, `static/`, rutas Jinja2 `/`, `/upload`, `/licitaciones`, `/calendario`,
`/historial`, `/guia`), los endpoints legacy-only de descarga (`/descargar/{...}`,
`/api/documentos/{id}/descargar`) y `routers/licitaciones.py` (`/api/licitaciones/*`,
CRUD de una tabla `licitaciones` que ya no existe — ver `decisiones.md`). `/procesar`
responde JSON exclusivamente. El resto de este documento describe el estado previo a T2
donde no se indica lo contrario; ver los documentos de módulo para el detalle.

Este documento cubre 10 archivos — el resto de `services/extraccion/`
(`robot.py`, `robot_comparativas.py`, `parsers.py`, `config.py`, `gemini_errors.py`) es
el módulo "Extracción IA", documentado por separado en
[`../extraccion_ia/`](../extraccion_ia/README.md).

| Archivo | Líneas | Rol |
|---|---|---|
| `main.py` | ~330 | Entrypoint FastAPI: `/procesar`, `/api/documentos*` — JSON puro desde T2. |
| `routers/extraction_results.py` | 60 | `PATCH /api/extraction-results/{id}` — vincula/desvincula un archivo a un proceso comercial y cambia su `document_type`. |
| `routers/clientes.py` | 54 | `GET /api/clientes` — selector de cliente real para el formulario de upload (§8). |
| `schemas/licitaciones.py` | 156 | Modelos Pydantic v2 — el nombre es histórico (compartidos con el router retirado), hoy solo los usa `extraction_results.py`. |
| `supabase_client.py` | 160 | Cliente Supabase singleton (feature flag), dedup de conexión y `resolver_drogueria_id_unica`. |
| `persistent_output.py` | 244 | SHA256, deduplicación (`buscar_duplicado_con_lock`) y `persistir_output_final` (INSERT de metadata en `extraction_results`). |
| `persistent_chunking.py` | 237 | CRUD de `processing_sessions` y `chunk_results`. |
| `background_tasks.py` | 202 | Wrapper de retry con backoff exponencial sobre `persistir_output_final`. |
| `auth.py` | 68 | Identificación JWT **opcional** para este backend, sobre `services/shared/auth_jwt.py`. |
| `procesos_comerciales_client.py` | 114 | Cliente de solo lectura cross-schema contra `procesos_comerciales` (schema de `presupuestacion/`), usado por `/procesar` y `GET /api/documentos`. |

Total: ~2151 líneas, leídas en su totalidad en esta sesión.

## Qué hace

- Expone `POST /procesar`, el único endpoint que ejecuta el pipeline completo: recibe el
  archivo, lo guarda en disco, calcula SHA256, deduplica, resuelve el formato-por-cliente
  (§8), crea una sesión de procesamiento, invoca `extraccion_ia` bajo un
  `asyncio.Semaphore(15)` (`main.py:67`, `:241`), lee el CSV resultante y agenda su
  persistencia como `BackgroundTask`. Ver [`flujo.md`](./flujo.md).
- Persiste metadata de extracciones (`extraction_results`), sesiones de procesamiento
  (`processing_sessions`) y chunks (`chunk_results`) en el schema nuevo de
  `presupuestacion/`, resolviendo `drogueria_id` del usuario autenticado. Ver
  [`base_de_datos.md`](./base_de_datos.md).
- Expone vinculación de archivos a procesos comerciales
  (`routers/extraction_results.py`) y listado de clientes activos
  (`routers/clientes.py`).
- Valida `proceso_comercial_id` (parámetro de formulario `licitacion_id`) contra la tabla
  `procesos_comerciales` del schema nuevo, escopeado por `drogueria_id`, vía
  `procesos_comerciales_client.py` — el cliente de solo lectura cross-servicio hacia el
  módulo [`procesos_comerciales`](../procesos_comerciales/) de `presupuestacion/`. Ver
  ahí [`casos_de_uso.md`](../procesos_comerciales/casos_de_uso.md) para el detalle desde
  el lado dueño de la tabla; este documento cubre solo la perspectiva del consumidor.

## Qué NO hace

- **No llama a Gemini directamente.** Ninguno de los 12 archivos de este módulo importa
  `google.generativeai`/`genai`. `main.py` importa `procesar_archivo`/
  `procesar_comparativa`/`parse_document` de `extraccion_ia` y los invoca dentro de
  `asyncio.to_thread` (`main.py:243-254`) — toda la lógica de prompts, chunking y
  fallback de parseo vive en ese otro módulo.
- **No persiste las filas extraídas (`rows`) en Supabase**, solo su metadata. El CSV en
  disco es la fuente de verdad — confirmado en el propio docstring de
  `persistent_output.py:9-12` y en `persistir_output_final` (`persistent_output.py:106-244`,
  el payload de INSERT nunca incluye `rows`). Ver RN-EXTRACCIONAPI-003 en
  [`reglas.md`](./reglas.md).
- **Ya no expone CRUD de licitaciones ni endpoints de descarga legacy.**
  `routers/licitaciones.py` (`/api/licitaciones/*`, tabla `licitaciones` inexistente),
  `/descargar/{nombre_archivo}` y `/api/documentos/{id}/descargar` se retiraron en T2
  junto con el HTML legacy que los consumía; el único validador de vinculación activo es
  `procesos_comerciales_client.py:validar_proceso_comercial_id`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — relación entre `main.py`/routers/persistencia,
  el patrón de servir HTML+JSON en el mismo endpoint y la tensión sobre la tabla
  `licitaciones`.
- [`base_de_datos.md`](./base_de_datos.md) — todas las tablas Supabase que toca este
  módulo, con columnas y operaciones CRUD.
- [`reglas.md`](./reglas.md) — reglas técnicas de negocio (RN-EXTRACCIONAPI-NNN).
- [`flujo.md`](./flujo.md) — flujo completo de `/procesar` y de la persistencia en
  background.
- [`estados.md`](./estados.md) — la máquina de estados de `processing_sessions.status`.
- [`casos_de_uso.md`](./casos_de_uso.md) — todos los endpoints, con evidencia de quién
  los consume.
- [`api.md`](./api.md) — funciones/endpoints públicos de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-EXTRACCIONAPI-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

## Relación con otros módulos

- [`../extraccion_ia/`](../extraccion_ia/README.md) — el pipeline de IA que este módulo
  invoca desde `/procesar`, sin persistir nada en Supabase por su cuenta.
- [`../core/`](../core/README.md) — `services/extraccion/auth.py` usa
  `services/shared/auth_jwt.py` (kernel de verificación JWT compartido, documentado ahí)
  para identificar opcionalmente al usuario.
- [`../procesos_comerciales/`](../procesos_comerciales/README.md) — dueño real de la
  tabla `procesos_comerciales` que `procesos_comerciales_client.py` consulta de solo
  lectura desde este módulo.
