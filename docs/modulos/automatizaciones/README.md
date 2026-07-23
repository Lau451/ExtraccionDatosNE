# Módulo Automatizaciones — `services/presupuestacion/automatizaciones/`

## Qué es

Automatizaciones es el motor de reglas evento-condición-acción ("if this then that") de
`presupuestacion/`: cada fila de `reglas_automatizacion` describe "cuando ocurre
`evento_disparador` sobre `entidad_objetivo` y se cumple `condicion` → ejecutar
`tipo_accion` con `parametros_accion`", y cada ejecución (o intento de ejecución) queda
registrada como una fila de `acciones_ejecutadas`, que además funciona como cola de
reintentos con backoff exponencial para las reglas en `modo_ejecucion = "cola"`.

Con 730 líneas de código repartidas en 5 archivos (`__init__.py` 0, `models.py` 69,
`repository.py` 83, `service.py` 267, `router.py` 54 — contadas con `wc -l` en esta
sesión) y `tests/automatizaciones/` con 239 líneas (`test_service.py`) y 18 líneas
(`conftest.py`), es un módulo más chico que Eventos (788+367 líneas) pero con un motor
de reglas genuino: evalúa condiciones, decide ejecución inmediata vs encolada, y
reintenta con backoff.

## Qué NO hace HOY (crítico)

**Nada en el código de producción llama a `disparar_reglas()` ni a
`procesar_acciones_pendientes()`.** Es el hallazgo central de este módulo, con cita
textual del propio código (`service.py:148-154`, dentro del docstring de
`disparar_reglas`):

> "Nota de alcance: esta función y `procesar_acciones_pendientes()` están completas y
> testeadas, pero HOY nada en el código las llama fuera de los tests -- ningún flujo de
> negocio (confirmar una OC, adjudicar una licitación, etc.) dispara `disparar_reglas()`,
> y no existe un worker/cron real que corra `procesar_acciones_pendientes()` ni el
> scheduler de `eventos.generar_instancias_recurrentes()` periódicamente. Es exactamente
> el "motor mínimo, sin conectar a los eventos de negocio todavía" que pedía el spec para
> esta ronda -- conectarlo es la próxima ronda, no una omisión de esta."

Confirmado también por `Grep` exhaustivo de `disparar_reglas|procesar_acciones_pendientes`
en todo el repositorio en esta sesión: los únicos call sites fuera de la propia
declaración en `service.py` están en `tests/automatizaciones/test_service.py` y en texto
de documentación (`ROADMAP.md:55-60`, `docs/modulos/eventos/README.md:41`). Ningún
`router.py` de ningún módulo de negocio (`procesos_comerciales`, `compras`,
`presupuestos`, etc.) importa ni llama a estas dos funciones. Ver
[`pendientes.md`](./pendientes.md) para el detalle completo — es el P1 más alto de los
módulos documentados hasta ahora, porque a diferencia de Eventos (donde solo la
recurrencia queda inerte) acá **todo el motor** —evaluación de condiciones, ejecución
inmediata, cola con reintentos— queda sin ningún disparador real.

Además:

- **Solo 2 de los 8 `tipo_accion` posibles están implementados.** `models.py:10-13`
  declara `crear_evento`, `crear_oc`, `enviar_notificacion`, `enviar_email`,
  `enviar_whatsapp`, `ejecutar_agente_ia`, `cambiar_estado`, `webhook`; `_ejecutar_accion`
  (`service.py:87-131`) solo implementa `crear_evento` (`:99-110`) y `enviar_notificacion`
  (`:112-129`) — cualquier otro valor cae en el `return False, f"tipo_accion '...' no
  implementado aún"` de `service.py:131`. Ver [`reglas.md`](./reglas.md).
- **`COLUMNA_FK_POR_ENTIDAD` cubre 5 de las 7 `entidad_objetivo` posibles.**
  `repository.py:9-15` mapea `proceso_comercial`, `comparativa`, `orden_compra`,
  `presupuesto` y `evento` a su columna FK en `acciones_ejecutadas`; el `Literal`
  `EntidadObjetivo` (`models.py:6-9`) admite además `extraction_result` y `entrega`, que
  no tienen columna equivalente porque el `CHECK ck_ae_una_entidad`
  (`docs/schema/extractor_final.sql:933-939`) de `acciones_ejecutadas` solo cubre 5
  columnas FK (`proceso_comercial_id`, `comparativa_id`, `orden_compra_id`,
  `presupuesto_id`, `evento_id`). Una regla con `entidad_objetivo` en
  `extraction_result`/`entrega` se **omite en silencio** (con `logger.warning`) al
  disparar — ver `service.py:162-169` y [`base_de_datos.md`](./base_de_datos.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `automatizaciones/__init__.py` | Vacío. |
| `automatizaciones/models.py` | 3 `Literal` (`EntidadObjetivo` 7 valores, `TipoAccion` 8 valores, `ModoEjecucion` 2 valores) y 4 modelos Pydantic para `reglas_automatizacion` y las métricas. |
| `automatizaciones/repository.py` | Acceso a datos puro sobre `reglas_automatizacion`, `acciones_ejecutadas` y la vista `v_metricas_automatizacion`, más el diccionario `COLUMNA_FK_POR_ENTIDAD`. |
| `automatizaciones/service.py` | CRUD de reglas, el motor (`_evaluar_condicion`, `_ejecutar_accion`, `disparar_reglas`, `procesar_acciones_pendientes`) y wrappers `_para_endpoint`. |
| `automatizaciones/router.py` | 4 endpoints HTTP: listar/crear/actualizar reglas y métricas. Sin `DELETE` (ver [`casos_de_uso.md`](./casos_de_uso.md)). |

## Dependencias

Depende de Core (`core/database.py`, `core/exceptions.py`, `core/auth.py`) y, a
diferencia de todos los módulos documentados hasta ahora, **importa código Python de
otros dos módulos de negocio**: `eventos.models.EventoCreate` / `eventos.service.
crear_evento` (`service.py:14-15`) y `notificaciones.service.crear_notificacion`
(`service.py:16`). Es el único consumidor confirmado de `eventos/` desde otro módulo de
negocio (confirmado del lado de `eventos/` en `docs/modulos/eventos/README.md:78-84` y
`casos_de_uso.md:45-59` de esa misma documentación). `notificaciones/` **todavía no está
documentado** — se documentará como el próximo módulo de esta serie; este hallazgo
cruzado queda registrado acá con la evidencia exacta de línea
(`services/presupuestacion/notificaciones/service.py:11-24`, función `crear_notificacion`)
para no perderlo. Ver [`arquitectura.md`](./arquitectura.md) para el detalle completo.

## Quién lo consume

- `services/presupuestacion/main.py:8`, `:55` monta `automatizaciones_router` sin
  prefijo adicional (`tags=["automatizaciones"]`).
- Nadie más en el repositorio importa código Python de `automatizaciones/` — confirmado
  por `Grep` de `from services.presupuestacion.automatizaciones` en todo el
  repositorio en esta sesión, sin coincidencias fuera del propio módulo, `main.py` y
  `tests/automatizaciones/`.
- En producción, el único uso real del módulo es administrativo: crear/listar/actualizar
  reglas y ver métricas vía HTTP. El motor (disparar/procesar) solo se ejerce desde los
  tests de integración.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — modelo evento-condición-acción, dependencias
  hacia `eventos/` y `notificaciones/`, por qué el motor está desconectado.
- [`base_de_datos.md`](./base_de_datos.md) — tablas `reglas_automatizacion` y
  `acciones_ejecutadas`, columnas, `CHECK`s, vista `v_metricas_automatizacion`, y la
  cobertura incompleta de `COLUMNA_FK_POR_ENTIDAD`.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-AUTOMATIZACIONES-NNN).
- [`flujo.md`](./flujo.md) — flujo de `disparar_reglas` y de `procesar_acciones_pendientes`
  con el backoff de reintentos.
- [`estados.md`](./estados.md) — máquina de estados de `acciones_ejecutadas` (cola de
  reintentos), incluyendo 2 valores del `CHECK` de BD que ningún código escribe jamás.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 4 endpoints, roles, y por qué no hay
  `DELETE` de reglas.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-AUTOMATIZACIONES-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3, con foco en la
  ausencia confirmada de disparador real para todo el motor.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, ver
[`../core/`](../core/) — no se repite esa documentación acá. Para el modelo de eventos
que este módulo puede crear como efecto de una regla, ver [`../eventos/`](../eventos/).
