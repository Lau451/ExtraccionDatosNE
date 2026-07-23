# Módulo Comparativas — `services/presupuestacion/comparativas/`

> No confundir con el pipeline de "comparativas de precios" del backend legacy
> (`services/extraccion/robot_comparativas.py`, documentado en
> [`../extraccion_ia/`](../extraccion_ia/)), que genera el CSV crudo con IA. Tampoco
> confundir con `services/presupuestacion/extraccion/` (documentado como
> "Extracción-Validación" en [`../extraccion_validacion/`](../extraccion_validacion/)),
> que es el módulo que **crea** las filas de `comparativas`/`ofertas_items` que este
> módulo consume. Este módulo es la contraparte de negocio, más chica: expone lectura
> curada de esas filas y un único caso de escritura acotado.

## Qué es

Comparativas es una fachada delgada de solo lectura sobre dos vistas SQL
(`v_renglones_ganados`, `v_ofertas_sin_matchear`), más un único caso de uso de
escritura (`asignar_proveedor`) que vincula manualmente un `proveedor_id` a una oferta
cuando no se pudo matchear automáticamente contra el catálogo de proveedores.

El módulo tiene 4 archivos con código, 171 líneas en total (verificado leyendo cada
archivo completo en esta sesión): `models.py` (29 líneas, 3 modelos Pydantic),
`repository.py` (48 líneas, 5 funciones de acceso a datos puro), `service.py` (34
líneas, 1 caso de uso + su wrapper para el endpoint) y `router.py` (60 líneas, 3
endpoints). `__init__.py` está vacío.

No tiene lógica de negocio propia para "ganar" un renglón o "matchear" una oferta —
ambos conceptos (`adjudicada`/`adjudicacion_estimada` y `proveedor_id`) ya están
resueltos en las tablas antes de que este módulo los lea o los toque. Ver
[`arquitectura.md`](./arquitectura.md).

## Qué NO hace

- **No genera comparativas ni ofertas.** `comparativas` y `ofertas_items` se crean en
  `_materializar_comparativa` del módulo `extraccion/` (documentado como
  "Extracción-Validación"), que este módulo solo lee. Ver
  [`../extraccion_validacion/flujo.md`](../extraccion_validacion/flujo.md) Flujo 2 —
  no se repite ese análisis acá.
- **No auto-detecta `es_drogueria_propia`.** Ningún archivo de este módulo lee, calcula
  ni escribe ese campo — ni siquiera `asignar_proveedor`, el único caso de escritura
  del módulo, que solo actualiza `proveedor_id` (`service.py:23-25`). Confirmado por
  `Grep` de `es_drogueria_propia` en los 4 archivos del módulo: cero resultados (solo
  aparece en `tests/comparativas/test_service.py`, como dato de fixture). Ver
  [`decisiones.md`](./decisiones.md) D-COMPARATIVAS-002 y
  [`pendientes.md`](./pendientes.md) para el impacto real de este gap.
- **No calcula `adjudicada`/`adjudicacion_estimada`.** Esos campos los escribe
  `_computar_posiciones` en `extraccion/service.py` (comparativa) y
  `confirmar_orden_compra` en `compras/service.py` (adjudicación oficial, aún sin
  documentar). Este módulo solo los lee, ya calculados, a través de
  `v_renglones_ganados`.
- **No usa auditoría (`core.audit`).** `Grep` de `core.audit`/`registrar_cambio`/
  `registrar_evento_ciclo_vida` en los 4 archivos: cero resultados. La escritura de
  `asignar_proveedor` no deja rastro en `historial_cambios` — ver
  [`pendientes.md`](./pendientes.md).
- **No tiene `estados.md`.** Ninguna tabla ni campo que este módulo toca tiene una
  máquina de estados propia dentro de este alcance: `ofertas_items.adjudicada`/
  `adjudicacion_estimada` son booleanos calculados fuera de este módulo (ver arriba),
  y `proveedor_id` es una FK que pasa de `NULL` a un valor una única vez, sin más
  transiciones ni reglas de estado — no amerita un documento de estados propio.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `comparativas/__init__.py` | Vacío. |
| `comparativas/models.py` | `AsignarProveedorRequest` (body del POST), `RenglonGanado` y `OfertaSinMatchear` (response models, uno por vista). |
| `comparativas/repository.py` | Acceso a datos puro: `buscar_oferta_item`, `buscar_proveedor`, `actualizar_oferta_item` (sobre `ofertas_items`/`proveedores`) y `listar_renglones_ganados`/`listar_ofertas_sin_matchear` (sobre las 2 vistas). |
| `comparativas/service.py` | `asignar_proveedor` (caso de uso, recibe `client` como parámetro) y `asignar_proveedor_para_endpoint` (wrapper que resuelve `get_service_client()`). |
| `comparativas/router.py` | 3 endpoints: 2 `GET` de lectura y 1 `POST` de escritura con validación de tenant inline. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:11,46`
(`app.include_router(comparativas_router, tags=["comparativas"])`), sin prefijo
propio. **Ningún frontend lo consume todavía**: `Grep` de `renglones-ganados`,
`sin-matchear` y `asignar-proveedor` en todo el repositorio no encontró ningún cliente
HTTP fuera del propio `router.py`. `frontend/PROGRESS.md:15` confirma la pantalla
correspondiente ("Comparativas") como `⬜ Pendiente`.

Este módulo no importa hacia otros módulos de negocio de `presupuestacion/` — solo
hacia `core/` (`core.database`, `core.exceptions`, `core.auth`). Es, en ese sentido,
un módulo hoja: no tiene dependientes internos conocidos ni dependencias salientes más
allá de `core/`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — las 2 vistas SQL de origen, relación con
  `extraccion_validacion/` (productor de datos) y `compras/` (consumidor cruzado de
  `es_drogueria_propia`).
- [`base_de_datos.md`](./base_de_datos.md) — las 2 vistas, la tabla `ofertas_items` y
  la tabla `proveedores`, con columnas y operaciones reales.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-COMPARATIVAS-NNN).
- [`flujo.md`](./flujo.md) — los 3 flujos del módulo, paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 3 endpoints, con roles y evidencia de
  quién los consume (nadie, todavía).
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-COMPARATIVAS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

## Relación con otros módulos

- [`../extraccion_validacion/`](../extraccion_validacion/README.md) — dueño real de
  `comparativas`/`ofertas_items`; produce las filas que este módulo lee y actualiza
  parcialmente (solo `proveedor_id`). Ver
  [`../extraccion_validacion/flujo.md`](../extraccion_validacion/flujo.md) Flujo 2 y
  [`../extraccion_validacion/decisiones.md`](../extraccion_validacion/decisiones.md)
  D-EXTRACCIONVALIDACION-001 (mismo motivo de negocio detrás de no auto-detectar
  `es_drogueria_propia`, confirmado también desde este lado — ver
  [`decisiones.md`](./decisiones.md) D-COMPARATIVAS-002).
- `compras/` (**sin documentación propia todavía** — confirmado con `Glob
  docs/modulos/compras/` en esta sesión, sin resultados) — `confirmar_orden_compra`
  (`compras/service.py:112-141`) lee `ofertas_items.es_drogueria_propia` para decidir
  si marca una oferta como `adjudicada=True` (`compras/service.py:130-131`). Es un
  hallazgo cruzado: el campo que este módulo no puede setear condiciona un flujo de
  otro módulo. Cuando `compras/` se documente, enlazar desde acá y desde ahí hacia
  este hallazgo.
- [`../core/`](../core/README.md) — `core.database` (`get_service_client`,
  `get_user_client`), `core.exceptions` (`NotFoundError`, `ValidationError`,
  `ForbiddenError`), `core.auth` (`require_roles`) — usados en este módulo, no se
  repite su documentación acá.
