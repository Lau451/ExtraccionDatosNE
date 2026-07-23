# Base de datos — Procesos Comerciales

Procesos Comerciales es el módulo dueño de la tabla `procesos_comerciales`, aunque no
es el único escritor: ver la sección de CRUD real más abajo.

## `procesos_comerciales`

| Columna | Qué hace este módulo (y quién más la toca) |
|---|---|
| `id` | PK. Generada por Postgres al insertar (`repository.py:12-13`). Usada como filtro `id=?` en los 7+ `SELECT` puntuales de otros módulos — ver [`arquitectura.md`](./arquitectura.md). |
| `drogueria_id` | FK a `droguerias`. Fijada al crear con la del solicitante (`service.py:44`); usada como filtro de tenant en `listar_procesos_comerciales` (`repository.py:22`). |
| `cliente_id` | Nullable (`ProcesoComercialCreate.cliente_id`, `models.py:24`). Escrita al crear (`service.py:45`), no leída por este módulo tras la escritura. |
| `clase` | `Clase` (`Literal["cotizacion", "licitacion"]`, `models.py:7`). Escrita al crear (`service.py:46`). Determina si se aplica RN-PROCESOS-001. Leída sin escribir por `extraccion/repository.py` y `pricing/repository.py` (ver arquitectura.md) para distinguir el flujo de cotización del de licitación. |
| `nombre` | NOT NULL. Escrita al crear (`service.py:47`). Usada para ordenar el listado (`repository.py:27`) y expuesta en `ProcesoComercialResumen` (`models.py:37`). |
| `categoria_id` | Nullable. Escrita al crear (`service.py:48`), no leída por este módulo tras la escritura. |
| `fecha` | Presente en `ProcesoComercialOut` (`models.py:49`) pero **no** aparece en el dict insertado por `crear_proceso_comercial` (`service.py:41-58`) — mismo patrón que `estado` (ver más abajo): el valor lo asigna un default de columna en la BD, no visible en este código Python. Hallazgo confirmado en esta relectura, no estaba en el descubrimiento previo. |
| `estado` | `Estado` (`Literal` de 8 valores, `models.py:9-18`). **No** aparece en el dict insertado por `crear_proceso_comercial` (`service.py:41-58`) — el valor inicial `"abierto"` lo asigna un default de columna en la BD (RN-PROCESOS-004, confirmado empíricamente por `tests/procesos_comerciales/test_service.py:30`). Leída como filtro en `listar_procesos_comerciales` (`repository.py:25-26`, RN-PROCESOS-002). El único `UPDATE` de esta columna en todo el repo vive en `presupuestos/repository.py:68-71` — ver [`estados.md`](./estados.md). |
| `monto_estimado` | Nullable, `Decimal`. Escrita al crear, serializada a `str` antes del INSERT (`service.py:49`). |
| `notas` | Nullable. Escrita al crear (`service.py:50`). |
| `apertura`, `vencimiento` | Nullable, `date`. Campos de seguimiento formal de licitación — no admitidos si `clase="cotizacion"` (RN-PROCESOS-001). Serializados a ISO antes del INSERT (`service.py:51-52`). |
| `tipo_gestion` | Nullable, `str`. Mismo régimen que `apertura`/`vencimiento` (RN-PROCESOS-001). Escrita al crear (`service.py:53`). |
| `modalidad` | `Modalidad` (`Literal["mail", "pliego"]`, `models.py:8`), nullable. Mismo régimen que `apertura`/`vencimiento` (RN-PROCESOS-001). Escrita al crear (`service.py:54`). |
| `comparativa_pedida` | `bool`, default `False` en `ProcesoComercialCreate` (`models.py:32`). Mismo régimen que `apertura`/`vencimiento` (RN-PROCESOS-001, con la particularidad de que se evalúa como `body.comparativa_pedida or None` para no disparar la guarda con el valor `False` por defecto — `service.py:26`). Escrita al crear (`service.py:55`). |
| `created_at`, `updated_at` | Expuestas en `ProcesoComercialOut` (`models.py:58-59`); no aparecen en el dict insertado — defaults de columna, no visibles en este código Python. |
| `created_by`, `updated_by` | Escritas ambas con el mismo `usuario_id` del solicitante al crear (`service.py:56-57`). No expuestas en `ProcesoComercialOut` ni en `ProcesoComercialResumen`. |
| `deleted_at` | Filtrada en el listado (`is_("deleted_at", None)`, `repository.py:23`), pero **ninguna** función leída en esta sesión (ni de este módulo ni de los consumidores de tabla) la escribe. No existe soft-delete implementado para esta tabla — ver [`pendientes.md`](./pendientes.md). |

## CRUD real sobre `procesos_comerciales` en todo el repositorio

A diferencia de Catálogo y Clientes, acá el CRUD está repartido en 5 módulos más 2
queries inline, y el único `UPDATE` **no** vive en el módulo dueño de la tabla:

| Operación | Archivo:línea | Notas |
|---|---|---|
| INSERT | `procesos_comerciales/repository.py:12-13` (`crear_proceso_comercial`) | Único punto de creación de la tabla. |
| SELECT (listado) | `procesos_comerciales/repository.py:16-27` (`listar_procesos_comerciales`) | Aplica RN-PROCESOS-002 si `activos=True`. |
| SELECT (por id) | `matching/repository.py:14-22` | `id, drogueria_id, cliente_id`. |
| SELECT (por id) | `extraccion/repository.py:13-21` (dentro de `presupuestacion/`) | `id, drogueria_id, cliente_id, clase`. |
| SELECT (por id) | `pricing/repository.py:135-143` | `id, drogueria_id, cliente_id, clase`. |
| SELECT (por id, inline) | `pricing/router.py:22-28` | `id, drogueria_id`, sin pasar por el repository. |
| SELECT (por id) | `compras/repository.py:6-14` | `id, drogueria_id, cliente_id`. |
| SELECT (por id, inline) | `compras/router.py:50-56` | `id, drogueria_id`, sin pasar por el repository. |
| SELECT (por id) | `presupuestos/repository.py:18-26` | `id, drogueria_id, clase, estado` — único que trae `estado`. |
| **UPDATE** | `presupuestos/repository.py:68-71` (`actualizar_proceso_comercial`) | **Único `UPDATE`** de la tabla en todo el repo. Invocado desde `presupuestos/service.py:239-241` para forzar `estado="presentado"`. Sin guarda de transición — ver [`estados.md`](./estados.md). |
| DELETE | — | No existe en ningún módulo leído en esta sesión. |

El router de `procesos_comerciales/` confirmado sin ningún PATCH/PUT: `router.py`
(40 líneas) solo define `GET` (`:22-30`) y `POST` (`:33-40`).
