# Pendientes — Auditoría técnica de Eventos

Clasificación P1 (ausencia de una capacidad esperada / riesgo estructural) / P2 (deuda
técnica relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión.

## P1 — Riesgo estructural

1. **`generar_instancias_recurrentes` no tiene ningún disparador real — funcionalidad
   "vestigial" hasta que se conecte.** [IMPLEMENTADO], confirmado por `Grep` exhaustivo
   de `cron|Celery|APScheduler|BackgroundScheduler|schedule.every|Procfile` en todo el
   repositorio (única coincidencia relevante: `supabase/migrations/0003_pg_cron_ttl.sql`,
   un job de TTL de sesiones de `services/extraccion/`, sin relación con `eventos`), por
   `Grep` de `generar_instancias_recurrentes` (ningún call site fuera de
   `eventos/service.py` y `tests/eventos/test_service.py`), y por texto explícito del
   propio equipo en `services/presupuestacion/ROADMAP.md:53-62` (citado completo en
   [`README.md`](./README.md)). El comentario de columna
   `eventos_recurrentes.proxima_ejecucion` ("Única columna que el scheduler consulta,
   por eso indexada", `extractor_final.sql:821`) confirma que la intención original
   siempre fue tener un scheduler — nunca se conectó. Toda la lógica de negocio
   (RN-EVENTOS-003) está completa y testeada
   (`tests/eventos/test_service.py:199-232`, `:332-353`); lo único que falta es lo que
   la invoque periódicamente. Mientras no se conecte, cualquier plantilla recurrente
   creada vía `POST /eventos-recurrentes` nunca generará instancias reales en producción
   — es funcionalidad completa pero inerte. Ver
   [`decisiones.md`](./decisiones.md) D-EVENTOS-004 para el detalle de por qué la
   función no filtra por tenant (coherente con un futuro job global).

2. **Ninguna de las dos transiciones de estado escritas por este módulo
   (`completar_evento`, `actualizar_evento` con `estado="cancelado"`) valida el estado
   anterior antes de aplicarse.** [IMPLEMENTADO], confirmado por lectura completa de
   `service.py:109-138` y `:141-164` — ninguna de las dos tiene un `if estado_actual
   not in (...): raise ConflictError(...)`. Consecuencias concretas: se puede completar
   un evento `"bloqueado"` sin que su dependencia se haya completado nunca (saltea por
   completo RN-EVENTOS-001); se puede cancelar o volver a completar un evento que ya
   está `"completado"` sin ningún error, generando filas de auditoría adicionales cada
   vez. No hay ningún test que ejercite estos casos límite. Ver
   [`estados.md`](./estados.md).

## P2 — Deuda técnica relevante

1. **Ninguna FK opcional salvo `depende_de_id` se valida contra su tabla de origen al
   crear un evento.** [IMPLEMENTADO] (RN-EVENTOS-005, `service.py:59-64`). Un
   `cliente_id`, `proveedor_id`, `proceso_comercial_id`, `comparativa_id` u
   `orden_compra_id` inexistente pasa sin error hasta que algo intente resolverlo (p.
   ej. `v_calendario`, que hace `LEFT JOIN clientes` y simplemente no trae nombre en vez
   de fallar). La mayoría de estas columnas no tiene `FK` declarada en el `CREATE TABLE`
   original (`extractor_final.sql:730-736`) — solo `responsable_id` la tiene, agregada
   después (`rls_final.sql:400`). No verificado en esta sesión si alguna migración
   posterior a `extractor_final.sql` agregó las FKs faltantes (fuera del alcance de los
   dos archivos de schema leídos).

2. **Ninguna protección contra un ciclo indirecto de dependencias de longitud ≥ 2.**
   [SUPOSICIÓN de riesgo, no confirmada con reproducción real] — el `CHECK
   ck_eventos_no_self` (`extractor_final.sql:770`) solo evita que un evento dependa de
   sí mismo directamente. No se encontró en `service.py` ni en el schema leído ningún
   mecanismo que impida crear el evento A dependiendo de B y, en una operación
   posterior, actualizar B para que dependa de A (nota: `EventoUpdate` no incluye
   `depende_de_id` entre sus campos editables, `models.py:32-40`, así que este ciclo
   concreto **no** sería alcanzable vía `PATCH` — solo sería un riesgo si algún futuro
   endpoint permitiera editar `depende_de_id` después de la creación). Ver
   [`decisiones.md`](./decisiones.md) D-EVENTOS-002.

3. **`regla_automatizacion_id` es una columna de `eventos` sin ningún código que la
   escriba en todo el repositorio.** [IMPLEMENTADO], confirmado por `Grep` de
   `regla_automatizacion_id`: solo aparece en el DDL, la `FK` a `reglas_automatizacion`
   y su índice (`extractor_final.sql:747`, `rls_final.sql`) — ni `eventos/models.py`
   (`EventoCreate`/`EventoOut` no la declaran) ni `automatizaciones/service.py` (que
   arma el evento con `EventoCreate(**campos_evento)`, un modelo sin ese campo) la
   tocan. Un evento creado por una regla de automatización (`origen="automatico"`) no
   deja rastro de **qué regla concreta** lo creó a nivel de columna estructurada —
   solo queda implícito en `metadata` si el llamador decide ponerlo ahí, o no queda en
   ningún lado. Ver [`base_de_datos.md`](./base_de_datos.md).

4. **`eventos_recurrentes` no tiene ninguna operación de borrado, ni soft ni duro.**
   [IMPLEMENTADO], confirmado por lectura completa de `repository.py` (128 líneas): no
   existe ninguna función `eliminar_evento_recurrente`/`soft_delete_evento_recurrente`,
   pese a que la tabla sí tiene columnas `deleted_at`/`deleted_by`
   (`extractor_final.sql:804-805`). La única forma de "apagar" una plantilla es
   `activa=False` vía `PATCH /eventos-recurrentes/{id}` (`EventoRecurrenteUpdate.activa`,
   `models.py:121`), que no es lo mismo que borrarla del listado.

## P3 — Menor

1. **`"en_progreso"` es un valor muerto del `Literal`/`CHECK` de `EstadoEvento`.**
   [IMPLEMENTADO], confirmado por `Grep` de `en_progreso` dentro de `eventos/`: aparece
   únicamente en la declaración del `Literal` (`models.py:10`) y en el `CHECK` de BD
   (`extractor_final.sql:762-764`) — ningún flujo de este módulo lo asigna nunca. Ver
   [`estados.md`](./estados.md).

2. **`"vencido"` solo existe como campo booleano derivado (`CalendarioItem.vencido`),
   nunca como valor real de la columna `eventos.estado`.** [IMPLEMENTADO]. Un evento con
   `fecha_limite` pasada sigue teniendo el `estado` que tuviera (`"pendiente"`,
   `"bloqueado"`, etc.) para siempre a nivel de columna; el vencimiento solo se ve
   reflejado al consultar `GET /calendario`, no al listar `GET /eventos` ni al leer
   `GET /eventos/{id}` directamente (`EventoOut` no tiene un campo `vencido`,
   `models.py:43-63`). Ver [`estados.md`](./estados.md).

3. **`crear_evento_recurrente` y `actualizar_evento_recurrente` no auditan**, a
   diferencia de las 4 operaciones de escritura de `eventos` (que sí lo hacen de forma
   sistemática — ver [`arquitectura.md`](./arquitectura.md)). [IMPLEMENTADO], confirmado
   por lectura completa de `service.py:238-293`: ninguna de las dos llama a
   `registrar_cambio`/`registrar_cambios`/`registrar_evento_ciclo_vida`. Crear o
   modificar una plantilla recurrente no deja rastro en `historial_cambios`; solo las
   **instancias** que esa plantilla genera (vía `generar_instancias_recurrentes`) sí
   quedan auditadas.

4. **`obtener_evento_recurrente` (repository) no filtra `deleted_at`**, a diferencia de
   `obtener_evento` (`repository.py:12-21`, que sí usa `.is_("deleted_at", None)`).
   [IMPLEMENTADO], confirmado comparando `repository.py:87-95` contra `:12-21`. No tiene
   consecuencia práctica hoy porque no existe ninguna función que escriba
   `deleted_at` sobre `eventos_recurrentes` (ver P2(4)), pero es una inconsistencia de
   patrón entre las dos tablas del mismo módulo.
