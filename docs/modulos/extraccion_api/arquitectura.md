# Arquitectura — API & Persistencia (legacy)

## Capas del módulo

```
                              main.py (FastAPI app)
                                     │
      ┌──────────────┬──────────────┼──────────────┬────────────────┐
      │              │              │               │                │
  Rutas HTML     /procesar      /api/documentos*  routers/*      auth.py
 (Jinja2, GET)  (POST, HTML     (GET, JSON puro)  (incluidos     (JWT opcional,
                 o JSON)                          con include_    Depends en
                                                    router)        /procesar)
      │              │              │               │
      │              ▼              ▼               ▼
      │      persistent_output.py  supabase_client.py   routers/licitaciones.py
      │      persistent_chunking.py  (singleton +        routers/extraction_results.py
      │      background_tasks.py     resolver_drogueria)  routers/clientes.py
      │              │                                         │
      │              └──────────────────┬──────────────────────┘
      │                                 ▼
      │                        Supabase (schema nuevo de
      │                        presupuestacion/: extraction_results,
      │                        processing_sessions, chunk_results;
      │                        + tabla legacy licitaciones)
      │
      ▼
  extraccion_ia (robot.py / robot_comparativas.py / parsers.py) — invocado
  solo desde main.py:/procesar, vía asyncio.to_thread bajo un Semaphore(15)
```

`main.py` es el único punto de entrada que conoce tanto a `extraccion_ia` (para
extraer datos) como a la capa de persistencia (para guardarlos). Los 3 routers
(`licitaciones`, `extraction_results`, `clientes`) son independientes entre sí — ninguno
importa a otro — y se registran con `app.include_router(...)` (`main.py:50-52`).
`procesos_comerciales_client.py` es consumido tanto por `main.py` (`/procesar`,
`GET /api/documentos`) como potencialmente por el frontend nuevo a futuro; deliberadamente
no importa nada de `routers/licitaciones.py` (`procesos_comerciales_client.py:9-11`).

## Servir HTML y JSON en el mismo endpoint

`POST /procesar` es simultáneamente la ruta que sirve el formulario HTML legacy y el
endpoint JSON que consume el frontend nuevo (`frontend/src/lib/api/extraccion.ts:42-58`,
función `procesarDocumento`). La decisión de formato de respuesta se resuelve en
`wants_json` (`main.py:80-83`):

```python
def wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    requested_with = request.headers.get("x-requested-with", "").lower()
    return "application/json" in accept or requested_with in {"fetch", "xmlhttprequest"}
```

`render_upload_response` (`main.py:86-101`) es el único punto de salida de `/procesar` en
todos sus caminos (éxito y cada rama de `except`): si `wants_json` es verdadero devuelve
un `JSONResponse` con `{ok, resultado?, error?, tipo?}`; si no, renderiza
`templates/index.html` con Jinja2, en ambos casos respetando el `status_code` HTTP que
corresponde al resultado (200, 409, 415, 422, 429, 500, 503). Ver
[`decisiones.md`](./decisiones.md) D-EXTRACCIONAPI-001 para el porqué de esta decisión
(no documentado explícitamente en el código, solo inferible).

Otros endpoints del módulo NO tienen esta ambigüedad: `GET /api/documentos*` siempre
devuelve JSON puro (`JSONResponse` directo, sin pasar por `render_upload_response`), y
los 3 routers (`licitaciones`, `extraction_results`, `clientes`) son APIs JSON puras vía
`response_model` de FastAPI. Solo `/procesar` mezcla ambos formatos en el mismo cuerpo de
función.

## La tabla `licitaciones`: tensión entre dos declaraciones del propio código

Existen dos afirmaciones contradictorias en el código sobre el estado de la tabla
`licitaciones`, ninguna de las cuales es verificable contra la base de datos real desde
esta sesión:

1. **`procesos_comerciales_client.py:7-11`** (docstring del módulo) afirma que
   `procesos_comerciales_client.py` "Reemplaza a
   `routers.licitaciones.validar_licitacion_id()` para el flujo de carga de documentos,
   porque esa tabla (`licitaciones`) **ya no existe**".
2. **`routers/licitaciones.py`** sigue consultando esa misma tabla activamente en 7
   endpoints (`listar`, `:96`; `listar_activas`, `:124`; `calendario`, `:143`;
   `obtener`, `:196`; `crear`, `:230`; `actualizar`, `:248,:256`; `eliminar`, `:286`), y
   el router sigue incluido en la app (`main.py:19,50`, `app.include_router(licitaciones_router)`).

Esta tensión está resuelta a nivel de **intención documentada**, aunque no a nivel de
**estado real de la base de datos**:

- `services/presupuestacion/ROADMAP.md:94-117` explica que `routers/licitaciones.py`
  está "atado al ciclo de vida del HTML legacy": el HTML viejo
  (`templates/licitaciones.html` → `static/licitaciones.js`,
  `templates/calendario.html` → `static/calendario.js`) sigue llamando activamente a
  `/api/licitaciones/activas`, `POST /api/licitaciones`, `GET/PATCH /api/licitaciones/{id}`
  y `/api/licitaciones/calendario` — confirmado por grep en esta sesión
  (`services/extraccion/static/licitaciones.js`, `calendario.js`). El mismo documento
  explicita: "aunque cada llamada real contra la tabla inexistente termine en error — el
  código sigue siendo el que sirve esas páginas hoy" (`ROADMAP.md:109-111`).
- El frontend nuevo (Vite/React) no tiene ningún call site contra `/api/licitaciones/*`
  (confirmado por grep en `frontend/` en esta sesión: la única referencia a rutas de este
  módulo es `frontend/src/lib/api/extraccion.ts`, que solo usa `/api/clientes`,
  `/api/documentos` y `/procesar`); usa en su lugar `POST/GET /procesos-comerciales` de
  `services/presupuestacion` (`ROADMAP.md:99-101`).
- `validar_licitacion_id` (`routers/licitaciones.py:45-75`) no tiene ningún call site
  activo confirmado en esta sesión (ni en `main.py`, ni en ningún router, ni en ningún
  test que lo invoque directamente aparte de definirlo) — solo se lo menciona en
  docstrings y documentos de `openspec/`. `/procesar` usa exclusivamente
  `validar_proceso_comercial_id` de `procesos_comerciales_client.py` (`main.py:174`,
  confirmado también por `tests/test_main_integration.py:325,362,393,417`, que mockean
  `services.extraccion.main.validar_proceso_comercial_id`, nunca
  `validar_licitacion_id`).

**Conclusión con evidencia de código**: la afirmación "la tabla ya no existe" describe la
intención de reemplazo del *flujo nuevo* de carga de documentos, no necesariamente el
estado físico de la tabla en la base de datos — que podría seguir existiendo (vacía o
no) para sostener las 2 páginas HTML legacy que aún dependen de ella. **Pendiente de
definición funcional**: si la tabla `licitaciones` existe hoy en la base de datos real,
esta documentación no puede confirmarlo ni descartarlo solo con evidencia de código. Ver
[`pendientes.md`](./pendientes.md) P1.

## Dos validadores de UUID en paralelo

| | `routers/licitaciones.py:validar_licitacion_id` | `procesos_comerciales_client.py:validar_proceso_comercial_id` |
|---|---|---|
| Tabla consultada | `licitaciones` | `procesos_comerciales` |
| Filtro de tenant | Ninguno | `.eq("drogueria_id", drogueria_id)` obligatorio |
| Usado por `/procesar` hoy | No (sin call site activo confirmado) | Sí (`main.py:174`) |
| Definido en | `routers/licitaciones.py:45-75` | `procesos_comerciales_client.py:30-77` |

Ambas funciones tienen la misma forma (UUID válido → existe en tabla → retorna el id o
lanza 422) pero apuntan a tablas distintas y ninguna importa a la otra
(`procesos_comerciales_client.py:9-11`, deliberado). Ver D-EXTRACCIONAPI-002 en
[`decisiones.md`](./decisiones.md).

## Cliente cross-schema hacia `procesos_comerciales`

`procesos_comerciales_client.py` usa `get_client()` (service_role, bypasea RLS), por lo
que el filtro `.eq("drogueria_id", drogueria_id)` es obligatorio en cada query — sin él,
cualquier consulta se ejecutaría contra `procesos_comerciales` de todas las droguerías de
la base (`procesos_comerciales_client.py:13-15`). El mismo criterio de acceso directo
(en vez de HTTP contra `services/presupuestacion`) se usa en `routers/clientes.py` para
leer `presupuestacion.clientes` (`routers/clientes.py:3-5`) — ambos backends comparten el
mismo proyecto de Supabase. Ver [`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)
para el detalle desde el lado dueño de la tabla.
