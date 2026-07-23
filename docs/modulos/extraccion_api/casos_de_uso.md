# Casos de uso — endpoints de API & Persistencia (legacy)

Consumidores confirmados por grep de esta sesión contra `frontend/` (Vite/React) y
`services/extraccion/static/*.js` (HTML legacy). Cuando no se encontró consumidor real,
se indica explícitamente.

## Rutas HTML (Jinja2)

| Método/Path | Handler | Rol |
|---|---|---|
| `GET /` | `home` (`main.py:107-109`) | Página de inicio, `home.html`. |
| `GET /licitaciones` | `licitaciones_page` (`main.py:112-114`) | Renderiza `licitaciones.html`, que carga `static/licitaciones.js` (consumidor de `/api/licitaciones/*`). |
| `GET /upload` | `upload_page` (`main.py:117-119`) | Formulario de carga, `index.html`. |
| `GET /calendario` | `calendario_page` (`main.py:356-358`) | Renderiza `calendario.html`, que carga `static/calendario.js` (consumidor de `/api/licitaciones/calendario`). |
| `GET /historial` | `historial_page` (`main.py:361-363`) | `historial.html`. |
| `GET /guia` | `guia_usuario` (`main.py:484-486`) | Sirve `docs/guia_usuario.html` como archivo estático. |

## `POST /procesar` — endpoint mixto (HTML legacy + JSON frontend nuevo)

- **Método/path**: `POST /procesar`.
- **Auth**: JWT opcional vía `Authorization: Bearer` (`get_usuario_id_actual`,
  `Depends`); sin roles.
- **Body**: `multipart/form-data` — `archivo` (requerido), `tipo`, `licitacion_id`,
  `cliente_id` (todos opcionales salvo `archivo`).
- **Response**: HTML (`index.html` re-renderizado) o JSON `{ok, resultado?, error?, tipo?}`
  según `Accept`/`X-Requested-With` (ver [`arquitectura.md`](./arquitectura.md)).
- **Consumidores confirmados**:
  - `frontend/src/lib/api/extraccion.ts:42-58` (`procesarDocumento`) — frontend nuevo,
    manda `archivo`, `tipo`, `licitacion_id`, `cliente_id`, espera JSON.
  - Formulario HTML legacy `templates/index.html` (submit nativo del form, sin
    confirmar el detalle del JS acompañante en esta sesión — fuera del alcance
    exhaustivo de `static/main.js`).

## `GET /api/documentos` y derivados

| Método/Path | Response | Consumidor confirmado |
|---|---|---|
| `GET /api/documentos?tipo=` | `{documentos: [...]}`, cada uno con `proceso_comercial: {id, nombre} \| null` | `frontend/src/lib/api/extraccion.ts:37-40` (`listarDocumentosRecientes`). |
| `GET /api/documentos/{doc_id}` | `{meta, rows}` — únicas rows leídas desde `comparativas_results`/`licitaciones_results` (tablas distintas de `extraction_results`, no cubiertas en `base_de_datos.md` porque no se encontró otro código de este módulo que las escriba) | Sin consumidor confirmado por grep en `frontend/`; **pendiente de definición fuera de alcance** de esta sesión. |
| `GET /api/documentos/{doc_id}/descargar` | CSV (`StreamingResponse`, `utf-8-sig`) | Sin consumidor confirmado por grep en `frontend/`; **pendiente de definición fuera de alcance**. |
| `GET /descargar/{nombre_archivo}?origen=&modulo=` | `FileResponse` del CSV en disco | Vinculado desde la respuesta de `/procesar` vía `params` (`main.py:248,255`, `urlencode`) — consumido por el HTML legacy tras la carga exitosa. |

## `routers/licitaciones.py` — `/api/licitaciones/*`

Todos sin autenticación (ningún `Depends` de auth en este router). Consumidor
confirmado: `static/licitaciones.js` y `static/calendario.js` (HTML legacy) — sin call
site en el frontend nuevo (ver tensión documentada en
[`arquitectura.md`](./arquitectura.md)).

| Método/Path | Roles | Response | Consumidor |
|---|---|---|---|
| `GET /api/licitaciones` | Ninguno | `LicitacionListResponse` paginado, filtros `estado`/`tipo`/`q` | `static/licitaciones.js` (listado). |
| `GET /api/licitaciones/activas` | Ninguno | `list[LicitacionActiva]` (solo `abierta`/`en_evaluacion`) | `static/licitaciones.js` (selector de upload legacy). |
| `GET /api/licitaciones/calendario?desde=&hasta=` | Ninguno | `list[LicitacionCalendario]` con `comparativa_estado` derivado | `static/calendario.js`. |
| `GET /api/licitaciones/{lic_id}` | Ninguno | `LicitacionDetalle` (+ `archivos` vinculados) | `static/licitaciones.js` (panel de detalle). |
| `POST /api/licitaciones` | Ninguno | `LicitacionOut`, 201 | `static/licitaciones.js` (alta). |
| `PATCH /api/licitaciones/{lic_id}` | Ninguno | `LicitacionOut` | `static/licitaciones.js` (edición). |
| `DELETE /api/licitaciones/{lic_id}` | Ninguno | 204 / 409 si tiene archivos vinculados | `static/licitaciones.js` (baja). |

## `routers/extraction_results.py` — `/api/extraction-results/*`

| Método/Path | Roles | Response | Consumidor confirmado |
|---|---|---|---|
| `PATCH /api/extraction-results/{result_id}` | Ninguno | `ExtractionResultOut` (incluye `licitacion_id`) | `static/licitaciones.js:178-181` (función `_patchExtraction`, HTML legacy) — vincula/desvincula un archivo a una licitación desde el panel de detalle. `openspec/changes/validar-extraccion/proposal.md:41-43` evalúa reusar este mismo endpoint para el flujo nuevo de "Validar extracción" del frontend Vite/React, sin confirmar en esta sesión si ya se implementó. |

## `routers/clientes.py` — `/api/clientes`

| Método/Path | Roles | Response | Consumidor confirmado |
|---|---|---|---|
| `GET /api/clientes` | Ninguno | `list[ClienteActivo]` (`id, nombre`), vacío si Supabase no disponible | `frontend/src/lib/api/extraccion.ts:33-35` (`listarClientes`) — selector de cliente en el formulario de upload nuevo (§8). |

## Resumen de auth por endpoint

Ningún endpoint de este módulo usa `require_roles` (patrón de `presupuestacion/core/`) —
consistente con el docstring de `auth.py:1-11`: "este servicio no tiene roles ni RLS
propios". Solo `/procesar` tiene algún tipo de identificación (opcional, ver
RN-EXTRACCIONAPI-008); el resto de los endpoints (routers + `/api/documentos*`) son
completamente anónimos a nivel de aplicación (protegidos, si acaso, por estar detrás de
`service_role` de Supabase y no exponer RLS).
