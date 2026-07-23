# Módulo Extracción-Validación — `services/presupuestacion/extraccion/`

> No confundir con `services/extraccion/` (backend legacy, documentado en
> [`../extraccion_api/`](../extraccion_api/) y [`../extraccion_ia/`](../extraccion_ia/)).
> Este módulo vive **dentro** del backend `presupuestacion` y es un módulo distinto,
> pese al mismo nombre de carpeta (`extraccion/`).

## Qué es

Extracción-Validación es el puente entre la extracción documental (IA) y las tablas de
negocio reales de `presupuestacion/`. Expone un único caso de uso —
`validar_extraccion` — que toma una fila ya procesada de `extraction_results`
(producida por el backend legacy `services/extraccion/`, ver
[`../extraccion_api/`](../extraccion_api/)) y la materializa: crea filas reales en
`items_proceso` (licitación/cotización, disparando matching automático) o en
`comparativas` + `ofertas_items` (comparativa, con versionado y notificación).

El módulo tiene 4 archivos con código: `models.py` (19 líneas), `repository.py` (103
líneas), `service.py` (320 líneas — el más largo, concentra toda la lógica de
materialización) y `router.py` (41 líneas). `__init__.py` está vacío. Todo verificado
leyendo cada archivo completo en esta sesión.

## Qué NO hace

- **No llama a Gemini ni procesa documentos.** El parseo IA ya ocurrió antes, en
  `services/extraccion/` (ver [`../extraccion_ia/`](../extraccion_ia/)). Este módulo
  solo lee el CSV ya generado (`extraction["csv_disk_path"]`,
  `service.py:24-26,69,145`) y lo vuelca en tablas de negocio.
- **No expone matching directamente.** Dispara `matching.service.procesar_matching_item`
  como efecto secundario de materializar una licitación/cotización
  (`service.py:15,88-91`), pero no tiene endpoints propios de matching — esos viven en
  el módulo `matching/` de `presupuestacion/`, documentado en
  [`../matching/`](../matching/README.md).
- **No implementa la materialización de `orden_compra`.** `document_type ==
  "orden_compra"` levanta `ValidationError` explícita — ver
  [`reglas.md`](./reglas.md) y [`decisiones.md`](./decisiones.md).
- **No pasa por `notificaciones.service.crear_notificacion`** al notificar el reemplazo
  de una comparativa vigente: inserta directo en la tabla `notificaciones`
  (`repository.py:101-102`), sin generar filas en `notificacion_entregas` ni respetar
  preferencias de canal — ver [`pendientes.md`](./pendientes.md).
- **No usa auditoría (`core.audit`) en todo el flujo**, solo en la materialización de
  comparativas — ver [`pendientes.md`](./pendientes.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `extraccion/__init__.py` | Vacío. |
| `extraccion/models.py` | `DocumentType` (Literal de 4 valores), `ValidarExtraccionRequest` (body del endpoint) y `ResultadoValidarExtraccion` (response model). |
| `extraccion/repository.py` | Acceso a datos puro: 11 funciones sobre `extraction_results`, `procesos_comerciales` (solo lectura), `items_proceso`, `comparativas`, `ofertas_items`, `usuarios` (solo lectura) y `notificaciones`. |
| `extraccion/service.py` | El caso de uso `validar_extraccion` y sus 6 helpers privados: resolución de `proceso_comercial_id`, materialización de licitación/cotización, materialización de comparativa (con versionado y notificación), cómputo de posición de precio. |
| `extraccion/router.py` | 1 endpoint HTTP: `POST /extracciones/{extraction_id}/validar`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:45`
(`app.include_router(extraccion_router, tags=["extraccion"])`), import en
`main.py:16`. Es el único punto de entrada HTTP de este módulo — no se encontró en
esta sesión ningún otro módulo de `presupuestacion/` que importe
`extraccion/service.py` o `extraccion/repository.py`.

Este módulo sí importa hacia afuera: `matching.service.procesar_matching_item`
(`service.py:15`) es la única dependencia hacia un módulo de negocio de otro dominio
dentro de `presupuestacion/` — ver [`arquitectura.md`](./arquitectura.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — el flujo cross-backend (quién produce
  `extraction_results`, quién lo consume), la dependencia hacia `matching/` y el
  bypass de `notificaciones/`.
- [`base_de_datos.md`](./base_de_datos.md) — tablas tocadas, columnas y CRUD real.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-EXTRACCIONVALIDACION-NNN).
- [`flujo.md`](./flujo.md) — flujo de validación de licitación/cotización y de
  comparativa, paso a paso.
- [`estados.md`](./estados.md) — el flag `extraction_results.validado` y el
  versionado de `comparativas.es_vigente`.
- [`casos_de_uso.md`](./casos_de_uso.md) — el único endpoint, con evidencia de quién
  lo consume.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-EXTRACCIONVALIDACION-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

## Relación con otros módulos

- [`../extraccion_api/`](../extraccion_api/README.md) — el backend legacy que produce
  la fila de `extraction_results` que este módulo consume (`INSERT` en
  `persistent_output.py:212-219` del otro backend; `SELECT` en
  `repository.py:6-10` de este). El CSV en disco (`csv_disk_path`) es el punto de
  contacto real entre ambos backends — ninguno de los dos persiste las filas
  extraídas en una tabla intermedia.
- [`../core/`](../core/README.md) — `core.database` (`get_service_client`,
  `get_user_client`), `core.exceptions` (`NotFoundError`, `ConflictError`,
  `ValidationError`, `ForbiddenError`), `core.auth` (`require_roles`) y `core.audit`
  (`registrar_cambio`, `registrar_evento_ciclo_vida`) — usados en este módulo, no se
  repite su documentación acá.
- [`../matching/`](../matching/README.md) — `_materializar_licitacion` llama a
  `matching.service.procesar_matching_item` por cada renglón creado
  (`service.py:88-91`); es el único consumidor de ese módulo, confirmado también
  desde el lado de `matching/` (ver [`../matching/README.md`](../matching/README.md)).
