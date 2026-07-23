# Módulo Procesos Comerciales — `services/presupuestacion/procesos_comerciales/`

## Qué es

Procesos Comerciales es el punto de entrada del pipeline comercial de `presupuestacion/`:
crea y lista los registros de `procesos_comerciales` — licitaciones y cotizaciones — que
después consumen `matching/`, `presupuestos/`, `pricing/`, `compras/` y el módulo
`extraccion/` de `presupuestacion/` para armar un presupuesto. Es el módulo dueño de la
tabla `procesos_comerciales`.

El módulo tiene 4 archivos con código, 209 líneas en total (`models.py` 59,
`repository.py` 27, `service.py` 83, `router.py` 40, `__init__.py` 0 — verificado
leyendo cada archivo en esta sesión), 2 endpoints, y es el primer módulo documentado de
`presupuestacion/` con una máquina de estados nominal real (`Estado`, `models.py:9-18`).

## Qué NO hace

- **No gestiona transiciones de estado**, pese a definir la máquina de estados nominal
  completa (`Estado`, `models.py:9-18`) y a usarla activamente en el listado
  (RN-PROCESOS-002). Ningún archivo de este módulo escribe la columna `estado`: ni
  `repository.py` (solo el INSERT inicial, que no incluye `estado`) ni `router.py`
  (solo GET/POST, sin PATCH/PUT). El único `UPDATE` de `estado` de toda la tabla vive
  en `presupuestos/repository.py`, fuera de este módulo — ver
  [`estados.md`](./estados.md) y [`arquitectura.md`](./arquitectura.md).
- **No expone ningún PATCH/PUT.** Confirmado leyendo `router.py` completo (40 líneas):
  solo `GET /procesos-comerciales` y `POST /procesos-comerciales`.
- **No borra procesos comerciales.** Existe la columna `deleted_at`, filtrada en el
  listado (`repository.py:23`), pero ninguna función de este módulo ni de ningún otro
  módulo leído en esta sesión la escribe — ver [`pendientes.md`](./pendientes.md).
- **No valida transiciones de estado en ningún punto del repo.** `presupuestos/` fuerza
  `estado="presentado"` sin verificar el estado anterior del proceso — ver
  [`estados.md`](./estados.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `procesos_comerciales/__init__.py` | Vacío. |
| `procesos_comerciales/models.py` | `Clase`, `Modalidad` y `Estado` (3 `Literal`) más `ProcesoComercialCreate`, `ProcesoComercialResumen` y `ProcesoComercialOut`. |
| `procesos_comerciales/repository.py` | Acceso a datos puro: `crear_proceso_comercial` (INSERT) y `listar_procesos_comerciales` (SELECT con filtro opcional de estados terminales). |
| `procesos_comerciales/service.py` | La guarda de negocio `_validar_campos_de_seguimiento`, `crear_proceso_comercial`, su wrapper `crear_proceso_comercial_para_endpoint` y el passthrough `listar_procesos_comerciales`. |
| `procesos_comerciales/router.py` | 2 endpoints HTTP. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:49`
(`app.include_router(procesos_comerciales_router, tags=["procesos_comerciales"])`),
import en `main.py:22`. Ningún otro módulo de `presupuestacion/` **importa**
`procesos_comerciales/` como módulo Python (confirmado por grep en esta sesión).

Sin embargo hay acoplamiento a nivel de tabla, sin pasar por este código, en 5 módulos
de `presupuestacion/` más 1 servicio externo — ver [`arquitectura.md`](./arquitectura.md)
y [`casos_de_uso.md`](./casos_de_uso.md) para el detalle completo:

- `matching/repository.py`, `extraccion/repository.py` (dentro de `presupuestacion/`),
  `pricing/repository.py` + `pricing/router.py`, `compras/repository.py` +
  `compras/router.py`: todos hacen `SELECT` puntual por `id` sobre `procesos_comerciales`.
- `presupuestos/repository.py`: hace el `SELECT` puntual y también el **único**
  `UPDATE` de `estado` de toda la tabla — ver [`estados.md`](./estados.md).
- Cross-servicio: `services/extraccion/procesos_comerciales_client.py` (114 líneas)
  valida existencia/pertenencia de un `proceso_comercial_id` y resuelve nombres en
  batch, con `service_role` (bypasea RLS).

`comparativas/`, `eventos/` y `automatizaciones/` **no** consultan `procesos_comerciales`
directamente (confirmado por grep en esta sesión) — no se los incluye como consumidores
de tabla para no sobre-reportar.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, acoplamiento a
  nivel de tabla con 5 módulos + 1 servicio externo, y el ciclo de vida partido con
  `presupuestos/`.
- [`base_de_datos.md`](./base_de_datos.md) — la tabla `procesos_comerciales`, columnas
  y CRUD real por módulo.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-PROCESOS-NNN).
- [`flujo.md`](./flujo.md) — los 3 flujos principales paso a paso.
- [`estados.md`](./estados.md) — la máquina de estados nominal, quién la lee, quién la
  escribe y la ausencia confirmada de guardas de transición.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 2 endpoints y la tabla completa de
  consumidores de la tabla.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-PROCESOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client` y el mecanismo de
auditoría (`registrar_evento_ciclo_vida`) que este módulo sí usa en la creación, ver
[`../core/`](../core/) — no se repite esa documentación acá.
