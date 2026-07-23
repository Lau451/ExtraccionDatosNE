# Módulo Eventos — `services/presupuestacion/eventos/`

## Qué es

Eventos es el motor de tareas/acciones operativas de `presupuestacion/`: cada fila de
`eventos` es una tarea concreta (llamar a un cliente, recibir mercadería, facturar,
hacer seguimiento) que puede colgar de un proceso comercial, una comparativa, una orden
de compra, un cliente o un proveedor, y que puede depender de otro evento anterior. El
calendario del sistema (`GET /calendario`) es una vista sobre esta misma tabla, no una
entidad separada.

El módulo tiene dos responsabilidades bien diferenciadas dentro de un mismo archivo de
servicio:

1. **Eventos puntuales** (`eventos`): alta, lectura, listado, actualización parcial,
   completar y soft-delete, con una regla de **dependencia lineal** entre eventos
   (`depende_de_id`) que bloquea el nacimiento de un evento y lo desbloquea en cascada
   cuando el evento del que depende se completa.
2. **Eventos recurrentes** (`eventos_recurrentes`): plantillas con una regla `RRULE`
   (RFC 5545, vía `dateutil.rrule`) que, si se ejecuta, materializan instancias
   puntuales en `eventos` y recalculan su propia próxima ejecución.

Con 788 líneas de código repartidas en 5 archivos (`__init__.py` 0, `models.py` 140,
`repository.py` 128, `service.py` 378, `router.py` 142 — contadas con `wc -l` en esta
sesión) es el archivo/módulo más grande de los 8 subdominios de soporte documentados
hasta ahora. `tests/eventos/` agrega 367 líneas (`conftest.py` 15, `test_service.py`
352) con 15 tests de integración, todos marcados `@pytest.mark.integration`.

## Qué NO hace

- **No tiene un disparador real para la recurrencia.** `generar_instancias_recurrentes`
  (`service.py:316-378`) es un "job periódico" solo en su docstring: no existe ningún
  cron, worker, `Celery`, `APScheduler` ni llamada periódica en todo el repositorio que
  lo invoque. Confirmado por `Grep` exhaustivo en esta sesión (`cron|Celery|APScheduler|
  BackgroundScheduler|schedule.every|Procfile`, sin resultados relevantes fuera de la
  migración `0003_pg_cron_ttl.sql`, que es un job de limpieza de
  `processing_sessions`/`chunk_results` del backend de **extracción**, sin relación con
  `eventos`) y por texto explícito del propio equipo en
  `services/presupuestacion/ROADMAP.md:53-62`:

  > "`disparar_reglas()`/`procesar_acciones_pendientes()` (`automatizaciones/service.py`)
  > y `generar_instancias_recurrentes()` (`eventos/service.py`) están completos y con
  > tests de integración, pero ninguno está conectado a un disparador real: no hay
  > cron/worker corriendo (...) periódicamente."

  Hoy la única forma de ejecutar `generar_instancias_recurrentes` es invocarla a mano o
  desde un test (`tests/eventos/test_service.py:216`, `:349`). Ver
  [`pendientes.md`](./pendientes.md) P1(1).
- **No valida que `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`,
  `cliente_id` o `proveedor_id` existan.** `crear_evento` (`service.py:33-82`) solo
  valida la existencia de `depende_de_id` (`service.py:42-45`); las otras 5 FKs
  opcionales se insertan tal cual vienen del body, sin `SELECT` previo. Ver
  [`reglas.md`](./reglas.md) y [`pendientes.md`](./pendientes.md).
- **No expone ningún `DELETE` de `eventos_recurrentes`** ni transición manual a
  `en_progreso`/`vencido` — ver [`estados.md`](./estados.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `eventos/__init__.py` | Vacío. |
| `eventos/models.py` | 4 `Literal` (`TipoEvento`, `EstadoEvento`, `Prioridad`, `OrigenEvento`) y 8 modelos Pydantic para `eventos` y `eventos_recurrentes`. |
| `eventos/repository.py` | Acceso a datos puro sobre `eventos`, `eventos_recurrentes`, `v_eventos_bloqueo` y `v_calendario`. |
| `eventos/service.py` | Toda la lógica de negocio: dependencia/bloqueo, desbloqueo en cascada, auditoría sistemática (`core/audit.py`), cálculo de `RRULE` y generación de instancias recurrentes. |
| `eventos/router.py` | 11 endpoints HTTP: 8 de `eventos`/calendario, 3 de `eventos_recurrentes`. |

## Dependencias

Solo depende de Core (`core/audit.py`, `core/database.py`, `core/exceptions.py`,
`core/auth.py` desde el router) y de la librería externa `dateutil.rrule`. No importa
ningún otro módulo de negocio de `presupuestacion/`. Ver
[`arquitectura.md`](./arquitectura.md) para el detalle completo con evidencia de línea.

## Quién lo consume

- `services/presupuestacion/main.py:15`, `:53` monta `eventos_router` sin prefijo
  adicional (`tags=["eventos"]`).
- `services/presupuestacion/automatizaciones/service.py:14-15` importa
  `EventoCreate` y `crear_evento` de este módulo, y los usa en
  `_ejecutar_accion` (`:99-110`) para materializar un evento cuando una regla
  de automatización dispara la acción `"crear_evento"`, pasando `origen="automatico"`
  explícitamente (`:108`). **Este es el único módulo de negocio que importa código
  Python de `eventos/`** (confirmado por `Grep` de
  `from services.presupuestacion.eventos` en todo el repositorio en esta sesión).
  `automatizaciones/` todavía no está documentado — se documentará completo en el
  próximo módulo; este hallazgo cruzado queda registrado acá con la evidencia exacta de
  línea para no perderlo.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, uso sistemático de
  auditoría, relación con `automatizaciones/`, dependencia externa `dateutil.rrule`.
- [`base_de_datos.md`](./base_de_datos.md) — tablas `eventos` y `eventos_recurrentes`,
  columnas, vistas y CRUD real.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-EVENTOS-NNN).
- [`flujo.md`](./flujo.md) — creación con dependencia, completar con desbloqueo en
  cascada, generación de instancias recurrentes.
- [`estados.md`](./estados.md) — máquina de estados de un evento, con diagrama y
  guardas reales.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 11 endpoints, roles, y el consumidor
  cruzado (`automatizaciones/`) con evidencia.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-EVENTOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3, con foco en la
  ausencia confirmada de scheduler real.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client` y el mecanismo de
auditoría que este módulo sí usa de forma sistemática (a diferencia de otros ya
documentados), ver [`../core/`](../core/) — no se repite esa documentación acá.
