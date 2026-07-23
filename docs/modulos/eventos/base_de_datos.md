# Base de datos — Eventos

Eventos es dueño exclusivo de dos tablas y dos vistas de solo lectura. A diferencia de
`procesos_comerciales`, no se encontró en esta sesión ningún otro módulo de
`presupuestacion/` que lea o escriba estas tablas directamente — el único acoplamiento
de negocio pasa por `eventos/service.py:crear_evento` (ver [`arquitectura.md`](./arquitectura.md)).

Definiciones verificadas en `docs/schema/extractor_final.sql:721-822` (tablas) y
`docs/schema/rls_final.sql:399-450`, `:505-518` (FKs y RLS agregadas después).

## `eventos`

| Columna | Tipo / constraint | Qué hace este módulo |
|---|---|---|
| `id` | `UUID`, PK, `gen_random_uuid()` | Generada por Postgres al insertar (`repository.py:8-9`). |
| `drogueria_id` | `UUID NOT NULL` | Fijada al crear con la del solicitante (`service.py:52`); filtro de tenant en todo `listar_eventos`/`calendario` (`repository.py:32`, `:73`). |
| `tipo` | `TEXT`, `CHECK` de 13 valores | `TipoEvento` (`models.py:6-9`), espejo exacto del `CHECK` de la BD (`extractor_final.sql:757-761`). Escrita al crear (`service.py:53`), no modificable por `EventoUpdate` (`models.py:32-40`). |
| `titulo` | `TEXT NOT NULL` | Escrita al crear (`service.py:54`), modificable por `PATCH` (`models.py:33`). |
| `descripcion` | `TEXT NULL` | Igual que `titulo`. |
| `estado` | `TEXT`, `CHECK` de 6 valores, default `'pendiente'` | `EstadoEvento` (`models.py:10`). Calculado por el service, nunca por un default de columna en este flujo — ver [`estados.md`](./estados.md). |
| `prioridad` | `TEXT`, `CHECK` de 4 valores, default `'media'` | `Prioridad` (`models.py:11`). Escrita al crear con el default del `BaseModel` si no viene (`models.py:19`), modificable por `PATCH`. |
| `origen` | `TEXT`, `CHECK` de 4 valores, default `'usuario'` | `OrigenEvento` (`models.py:12`). Parámetro `origen` de `crear_evento`, default `"usuario"` (`service.py:39`); `generar_instancias_recurrentes` fuerza `"sistema"` (`:331`); `automatizaciones/` fuerza `"automatico"` (ver [`arquitectura.md`](./arquitectura.md)). Alimenta el mapeo a `historial_cambios.origen` — RN-EVENTOS-004. |
| `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`, `cliente_id`, `proveedor_id`, `responsable_id` | `UUID NULL` (sin `FK` declarada en el `CREATE TABLE`, comentario "relaciones opcionales", `extractor_final.sql:730-736`) | Escritas tal cual vienen del body al crear (`service.py:59-64`); **ninguna se valida contra su tabla de origen** — ver RN-EVENTOS-005 en [`reglas.md`](./reglas.md). `responsable_id` sí tiene `FK` a `usuarios` agregada después (`rls_final.sql:400`). |
| `depende_de_id` | `UUID NULL`, `CHECK ck_eventos_no_self` (no puede depender de sí mismo) | Única FK opcional que **sí** se valida en el service (RN-EVENTOS-001). Comentario de la columna (`extractor_final.sql:776`) documenta explícitamente el modelo lineal — ver D-EVENTOS-002. |
| `evento_recurrente_id` | `UUID NULL` | Solo la escribe `generar_instancias_recurrentes` (`service.py:335`), nunca `crear_evento`. Enlaza una instancia con su plantilla. |
| `fecha_programada`, `fecha_limite` | `TIMESTAMPTZ NULL`, `CHECK ck_eventos_fechas` (`fecha_limite >= fecha_programada` si ambas están) | Serializadas a ISO antes del INSERT/UPDATE (`service.py:66-67`, `:114-116`). El `CHECK` de BD no tiene contraparte en Python — ninguna validación previa en `service.py` lo replica (a diferencia de `procesos_comerciales`, D-PROCESOS-003 equivalente no existe acá). |
| `fecha_real` | `TIMESTAMPTZ NULL` | Escrita únicamente por `completar_evento`, con `datetime.now(timezone.utc)` (`service.py:149`). |
| `metadata` | `JSONB NULL` | Passthrough sin validación de esquema interno — "JSONB para datos específicos del tipo de evento" (comentario `extractor_final.sql:777`). |
| `regla_automatizacion_id` | `UUID NULL`, `FK` a `reglas_automatizacion` (`rls_final.sql`, migración posterior a `extractor_final.sql`), indexada (`idx_ev_regla`) | **Columna sin ningún código que la escriba en todo el repositorio** — confirmado por `Grep` de `regla_automatizacion_id` en esta sesión: solo aparece en el DDL/FK/índice, nunca en `eventos/` ni en `automatizaciones/service.py` (que arma el evento con `EventoCreate`, un modelo que no declara este campo). Ver [`pendientes.md`](./pendientes.md). |
| `created_by`, `updated_by` | `UUID NULL`, FK a `usuarios` | Escritas con el `usuario_id` del solicitante en cada operación de escritura. |
| `deleted_at`, `deleted_by` | `TIMESTAMPTZ NULL` / `UUID NULL` | Escritas por `soft_delete_evento` (`repository.py:46-49`); `obtener_evento` a nivel repository **no** filtra `deleted_at` en `PATCH`/completar/eliminar (usa `.is_("deleted_at", None)` en `obtener_evento`, `repository.py:17`, así que sí filtra ahí; ver test `test_eliminar_evento_soft_delete`, que confirma que un `SELECT` directo sin ese filtro sigue viendo la fila). |
| `created_at`, `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | No aparecen en ningún INSERT/UPDATE de este módulo — defaults de columna. |

## `eventos_recurrentes`

| Columna | Tipo / constraint | Qué hace este módulo |
|---|---|---|
| `id`, `drogueria_id`, `tipo`, `titulo`, `descripcion`, `prioridad`, `responsable_id`, `cliente_id`, `proveedor_id`, `metadata` | Igual régimen que sus contrapartes de `eventos` | Escritas al crear (`service.py:249-259`), sin FKs opcionales adicionales (no tiene `proceso_comercial_id`/`comparativa_id`/`orden_compra_id`/`depende_de_id`). |
| `rrule` | `TEXT NOT NULL` | Regla RFC 5545. Validada por `dateutil.rrule.rrulestr` antes del INSERT (RN-EVENTOS-003). |
| `fecha_inicio` | `DATE NOT NULL` | Serializada a ISO (`service.py:260`). |
| `fecha_fin` | `DATE NULL`, `CHECK ck_er_fechas` (`>= fecha_inicio`) | Si está seteada, `generar_instancias_recurrentes` la usa para desactivar la plantilla cuando la próxima ejecución la supera (RN-EVENTOS-003). |
| `proxima_ejecucion` | `TIMESTAMPTZ NULL` | Calculada al crear (`service.py:243`, `:262`) y recalculada en cada corrida de `generar_instancias_recurrentes` (`:371`). Comentario de columna: "Única columna que el scheduler consulta, por eso indexada" (`extractor_final.sql:821`) — confirma la intención original de que existiera un scheduler, ver [`README.md`](./README.md). |
| `ultima_generacion` | `TIMESTAMPTZ NULL` | Escrita solo por `generar_instancias_recurrentes` (`:372`). |
| `instancias_generadas` | `INTEGER NOT NULL DEFAULT 0`, `CHECK >= 0` | Incrementada en 1 por cada instancia materializada (`:373`). |
| `activa` | `BOOLEAN NOT NULL DEFAULT TRUE` | Puede desactivarse manualmente (`EventoRecurrenteUpdate.activa`, `models.py:121`) o automáticamente cuando se supera `fecha_fin` (`service.py:358-365`). |
| `created_by`, `updated_by`, `deleted_at`, `deleted_by`, `created_at`, `updated_at` | Igual régimen que `eventos` | `soft_delete` de esta tabla **no tiene función en `repository.py`** — no existe `soft_delete_evento_recurrente`; la columna `deleted_at` está en el DDL pero ningún código de este módulo la escribe. |

## Vistas

| Vista | Definición | Quién la usa |
|---|---|---|
| `v_eventos_bloqueo` | `docs/schema/extractor_final.sql:1658-1674`. `puede_avanzar = (depende_de_id IS NULL OR dep.estado = 'completado')`. `security_invoker = on` (`:1715`). | `repository.py:63-67` (`bloqueo_de_evento`), expuesta en `GET /eventos/{id}/bloqueo`. |
| `v_calendario` | `docs/schema/rls_final.sql:424-450`. Joinea `usuarios` (nombre del responsable) y `clientes` (nombre del cliente); `vencido = fecha_limite < NOW()` salvo que `estado IN ('completado', 'cancelado')`. `security_invoker = on`. | `repository.py:70-78` (`calendario`), expuesta en `GET /calendario`. |

## RLS (`docs/schema/rls_final.sql:508-518`)

`INSERT`/`UPDATE` de ambas tablas requieren rol en
`('admin','gerencia','lider_comercial','comercial','compras')` más mismo tenant;
`DELETE` requiere `es_superadmin()`. Esta política de `DELETE` **no coincide** con la
autorización real del endpoint `DELETE /eventos/{id}`, que exige
`require_roles("admin", "gerencia")` (`router.py:89`) — no es una contradicción
explotable porque el borrado real pasa por `soft_delete_evento` (un `UPDATE`, no un
`DELETE` SQL) ejecutado con `service_client` (sin RLS), así que la política `ev_del`
nunca se evalúa en este flujo. Ver [`decisiones.md`](./decisiones.md).

## CRUD real (todas las funciones en `eventos/repository.py`)

| Tabla | Operación | Función | Línea |
|---|---|---|---|
| `eventos` | INSERT | `crear_evento` | `:8-9` |
| `eventos` | SELECT (por id) | `obtener_evento` | `:12-21` |
| `eventos` | SELECT (listado) | `listar_eventos` | `:24-39` |
| `eventos` | UPDATE | `actualizar_evento` | `:42-43` |
| `eventos` | UPDATE (soft delete) | `soft_delete_evento` | `:46-49` |
| `eventos` | SELECT (ids bloqueados por dependencia) | `listar_bloqueados_por_dependencia` | `:52-60` |
| `v_eventos_bloqueo` | SELECT | `bloqueo_de_evento` | `:63-67` |
| `v_calendario` | SELECT | `calendario` | `:70-78` |
| `eventos_recurrentes` | INSERT | `crear_evento_recurrente` | `:83-84` |
| `eventos_recurrentes` | SELECT (por id) | `obtener_evento_recurrente` | `:87-95` |
| `eventos_recurrentes` | SELECT (listado) | `listar_eventos_recurrentes` | `:98-104` |
| `eventos_recurrentes` | UPDATE | `actualizar_evento_recurrente` | `:107-116` |
| `eventos_recurrentes` | SELECT (candidatas a ejecutar) | `listar_recurrentes_a_ejecutar` | `:119-128` |

No existe `DELETE` real (SQL) sobre ninguna de las dos tablas en todo el módulo —
`eventos` tiene soft-delete vía `UPDATE`; `eventos_recurrentes` no tiene ninguna
operación de borrado, ni soft ni duro.
