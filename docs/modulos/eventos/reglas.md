# Reglas — Eventos

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`, `models.py`) y sus tests (`tests/eventos/test_service.py`) en esta
sesión.

### RN-EVENTOS-001 — Un evento con dependencia sin completar nace bloqueado

- **Descripción**: al crear un evento con `depende_de_id`, si el evento del que depende
  no existe se rechaza la creación; si existe pero su `estado` no es `"completado"`, el
  nuevo evento se crea directamente con `estado = "bloqueado"` en vez de `"pendiente"`.
- **Condición**: `body.depende_de_id is not None` (`service.py:42`).
- **Resultado**:
  - Dependencia inexistente → `ValidationError("El evento del que depende no existe")`
    (`service.py:44-45`), el INSERT nunca se ejecuta.
  - Dependencia existente con `estado != "completado"` → `estado = "bloqueado"`
    (`service.py:46-47`).
  - Dependencia existente con `estado == "completado"` → el evento nace `"pendiente"`
    igual que uno sin dependencia (el `if` de la línea 47 no se cumple).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/eventos/service.py:33-82` (`crear_evento`),
  específicamente `:41-47`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `tests/eventos/test_service.py:22-31`
  (`test_crear_evento_sin_dependencia_queda_pendiente`) y `:34-52`
  (`test_crear_evento_con_dependencia_no_completada_queda_bloqueado`). No hay ningún
  test en el archivo leído que cree un evento dependiendo de otro ya `"completado"`
  para confirmar el caso "nace pendiente" — cubierto por lectura de código, no por test.

### RN-EVENTOS-002 — Completar un evento desbloquea en cascada a sus dependientes directos

- **Descripción**: al completar un evento, además de marcarlo `"completado"`, se buscan
  todos los eventos `bloqueado` cuyo `depende_de_id` apunte a él y se los pasa a
  `"pendiente"` — uno por uno, cada uno con su propia fila de auditoría.
- **Condición**: cualquier llamada exitosa a `completar_evento`.
- **Resultado**: `repo.listar_bloqueados_por_dependencia(client, depende_de_id=evento_id)`
  (`service.py:166`, filtra `depende_de_id = evento_id AND estado = 'bloqueado'`,
  `repository.py:52-60`); cada resultado se actualiza a `estado = "pendiente"`
  (`service.py:167-169`) y se audita individualmente (`:170-181`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/eventos/service.py:141-183`
  (`completar_evento`), específicamente `:166-181`.
- **Observaciones**: [IMPLEMENTADO]. Es un desbloqueo de **un solo nivel**: si el
  evento recién desbloqueado (`bloqueado → pendiente`) tuviera a su vez otro evento
  dependiendo de él, ese tercer evento **no** se resuelve en la misma llamada, porque
  el desbloqueo solo cambia `estado`, nunca invoca recursivamente a `completar_evento`
  ni reevalúa transitivamente la cadena — la cascada real ocurre recién cuando alguien
  complete ese segundo evento en una llamada aparte. No hay ningún test ni código que
  encadene 3 eventos para verificar este límite; confirmado por lectura completa del
  cuerpo de la función (`:141-183`), no hay recursión ni loop sobre niveles adicionales.
  Verificado en `tests/eventos/test_service.py:56-81`
  (`test_completar_evento_desbloquea_dependientes`) y `:258-301`
  (`test_completar_evento_registra_historial_propio_y_del_dependiente`, confirma
  además que ambas filas de auditoría —la del evento completado y la del dependiente
  desbloqueado— quedan con `batch_id` propios: `completar_evento` genera un
  `uuid.uuid4()` distinto por cada llamada a `registrar_cambio`, `service.py:163`,
  `:180`, no comparte `batch_id` entre el evento propio y sus dependientes).

### RN-EVENTOS-003 — Generación de instancias recurrentes: materializa, recalcula y desactiva por `fecha_fin`

- **Descripción**: `generar_instancias_recurrentes` recorre todas las plantillas
  `activa = TRUE` con `proxima_ejecucion <= ahora`; por cada una, crea una instancia en
  `eventos` con `origen = "sistema"` y `evento_recurrente_id` apuntando a la plantilla,
  recalcula la próxima ejecución con la `RRULE`, y desactiva la plantilla si la próxima
  ejecución cae después de `fecha_fin` (o si ya no hay próxima ejecución y `fecha_fin`
  está seteada).
- **Condición**: se invoque la función (ver RN-EVENTOS-006 sobre la ausencia de
  disparador real).
- **Resultado**, por cada plantilla vencida (`service.py:316-378`):
  1. `repo.listar_recurrentes_a_ejecutar` trae las plantillas con
     `activa = True AND proxima_ejecucion <= now()` (`repository.py:119-128`).
  2. Se inserta una instancia en `eventos` con `estado = "pendiente"`,
     `origen = "sistema"`, `fecha_programada = plantilla["proxima_ejecucion"]`
     (`service.py:320-341`).
  3. Se audita como creación de ciclo de vida, `origen = "sistema"` (`:342-350`).
  4. Se recalcula `regla.after(ejecutada_en)` con `ejecutada_en =
     plantilla["proxima_ejecucion"]` como nuevo `dtstart` (`:353-355`).
  5. Si hay `fecha_fin` y la nueva `proxima` la supera (`proxima.date() >
     limite.date()`), se desactiva la plantilla y se descarta `proxima` (`:359-363`).
     Si no queda `proxima` (la `RRULE` se agotó, p. ej. `COUNT=1`) y hay `fecha_fin`
     seteada, también se desactiva (`:364-365`) — cubre el caso en que la regla termina
     antes de llegar a `fecha_fin`.
  6. Se actualiza la plantilla: nueva `proxima_ejecucion`, `ultima_generacion = now()`,
     `instancias_generadas += 1`, `activa` recalculada (`:367-376`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/eventos/service.py:316-378`.
- **Observaciones**: [IMPLEMENTADO], sin disparador real conectado — ver
  RN-EVENTOS-006/[`pendientes.md`](./pendientes.md). Verificado por
  `tests/eventos/test_service.py:199-232`
  (`test_generar_instancias_recurrentes_materializa_y_recalcula`) y `:332-353`
  (`test_generar_instancias_recurrentes_desactiva_al_superar_fecha_fin`). **Nota sobre
  `fecha_fin` sin `RRULE` con `COUNT`/`UNTIL`**: si una plantilla tiene `fecha_fin` pero
  su `RRULE` es infinita (p. ej. `FREQ=DAILY` sin límite), el paso 5 puede seguir
  desactivando correctamente porque compara `proxima.date()` contra `limite.date()` en
  cada corrida — no depende de que la propia `RRULE` termine.

### RN-EVENTOS-004 — Mapeo estricto de vocabularios entre `eventos.origen` y `historial_cambios.origen`

- **Descripción**: `eventos.origen` (`OrigenEvento`) y `historial_cambios.origen`
  (`OrigenCambio`, de `core/audit.py`) son vocabularios distintos para el mismo
  concepto — 3 de los 4 valores de `OrigenEvento` coinciden textualmente con
  `OrigenCambio`, pero `"automatico"` (eventos) se traduce a `"automatizacion"`
  (auditoría).
- **Condición**: cualquier llamada a `registrar_evento_ciclo_vida` con un `origen` que
  provenga de `crear_evento`.
- **Resultado**: `_ORIGEN_EVENTO_A_ORIGEN_CAMBIO[origen]` (`service.py:73-81`, usa el
  diccionario de `:24-29`) — nunca se pasa el `origen` de `eventos` directo al
  `registrar_evento_ciclo_vida` de la creación.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/eventos/service.py:20-29`.
- **Observaciones**: [IMPLEMENTADO]. Cita textual verificada del comentario que precede
  el diccionario (`service.py:20-23`):

  > "# eventos.origen usa 'automatico'; historial_cambios.origen usa 'automatizacion'
  > (mismo concepto, vocabulario distinto -- ver core/audit.py OrigenCambio).
  > dict[OrigenEvento, str] en vez de dict[str, str] para que agregar un valor a
  > OrigenEvento sin agregarlo acá rompa el chequeo de tipos, no falle en silencio
  > recién en runtime con un KeyError."

  El tipado `dict[OrigenEvento, str]` (`:24`) hace que un `Literal` de 4 valores
  (`models.py:12`) deba tener sus 4 claves presentes en el diccionario — si se agrega un
  quinto valor a `OrigenEvento` sin agregar su entrada acá, un chequeo de tipos estático
  (`mypy`/`pyright`) marcaría el diccionario como incompleto antes de llegar a
  ejecutarse; en runtime puro Python esto seguiría siendo un `KeyError` si el chequeo
  de tipos no corre en CI — no verificado en esta sesión si el repositorio corre un
  chequeo de tipos en CI (fuera de alcance). **Importante**: este mapeo solo se usa en
  `crear_evento` (creación) — `completar_evento`, `actualizar_evento` y
  `eliminar_evento` pasan `origen="usuario"` literal (`service.py:161`, `:134`, `:195`),
  sin pasar por el diccionario, porque esas operaciones no reciben un `OrigenEvento`
  parametrizable.

### RN-EVENTOS-005 — Ninguna FK opcional salvo `depende_de_id` se valida contra su tabla de origen

- **Descripción**: `crear_evento` recibe `proceso_comercial_id`, `comparativa_id`,
  `orden_compra_id`, `cliente_id`, `proveedor_id` y `responsable_id` como IDs opcionales
  y los inserta sin verificar que existan.
- **Condición**: cualquier creación de evento con alguno de estos campos seteado.
- **Resultado**: el `INSERT` se ejecuta igual aunque el ID no exista en su tabla de
  origen (sin `FK` declarada para la mayoría de estas columnas en el `CREATE TABLE`
  original — solo `responsable_id` tiene `FK` a `usuarios`, agregada en
  `rls_final.sql:400`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/eventos/service.py:33-82`, comparar el único
  `SELECT` de validación (`:43`, solo para `depende_de_id`) contra las 6 columnas
  restantes (`:59-64`), insertadas directo desde `body`.
- **Observaciones**: [IMPLEMENTADO]. No hay ningún test que cree un evento con, por
  ejemplo, un `cliente_id` inexistente para confirmar que no falla — se infiere del
  código, no de un test explícito. Si `proceso_comercial_id`/`comparativa_id`/
  `orden_compra_id`/`cliente_id`/`proveedor_id` no tienen `FK` real en la BD (no
  verificado más allá de lo leído en `extractor_final.sql:730-736`, que las declara sin
  `REFERENCES`), un ID arbitrario con formato UUID válido pasaría sin error hasta que
  algo intente resolverlo (p. ej. `v_calendario`, que hace `LEFT JOIN clientes` —
  simplemente no traería nombre). Ver [`pendientes.md`](./pendientes.md).

### RN-EVENTOS-006 — `generar_instancias_recurrentes` no tiene ningún disparador real

- **Descripción**: la función existe, está implementada por completo y tiene tests de
  integración, pero ningún proceso del repositorio la invoca fuera de los tests.
- **Condición**: siempre — es una ausencia estructural, no condicional.
- **Resultado**: las plantillas con `proxima_ejecucion` vencida se acumulan
  indefinidamente sin generar instancias hasta que alguien llame a la función a mano.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/eventos/service.py:316-378`.
- **Observaciones**: [IMPLEMENTADO] la ausencia del disparador, confirmada por `Grep`
  exhaustivo de `cron|Celery|APScheduler|BackgroundScheduler|schedule.every|Procfile`
  en todo el repositorio (sin resultados relevantes: la única coincidencia,
  `supabase/migrations/0003_pg_cron_ttl.sql`, es un job de TTL de
  `processing_sessions`/`chunk_results` del backend `services/extraccion/`, sin relación
  con `eventos`) y por texto explícito de `services/presupuestacion/ROADMAP.md:53-62`
  (citado completo en [`README.md`](./README.md)). Único call site fuera de tests: no
  existe ninguno — confirmado por `Grep` de `generar_instancias_recurrentes` en todo el
  repositorio. Ver [`pendientes.md`](./pendientes.md) P1(1).

### RN-EVENTOS-007 — `PATCH /eventos/{id}` solo permite una transición manual de estado: a `"cancelado"`

- **Descripción**: `EventoUpdate.estado` está tipado como `Literal["cancelado"] | None`,
  no como el `EstadoEvento` completo de 6 valores.
- **Condición**: cualquier `PATCH /eventos/{id}` que incluya `estado` en el body.
- **Resultado**: Pydantic rechaza con `422` cualquier valor de `estado` que no sea
  exactamente `"cancelado"` antes de que la request llegue a `actualizar_evento`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/eventos/models.py:39`.
- **Observaciones**: [IMPLEMENTADO]. No hay ningún test en
  `tests/eventos/test_service.py` que ejercite específicamente `estado="cancelado"` vía
  `actualizar_evento` — la única cobertura de `actualizar_evento` en los tests leídos es
  `test_actualizar_evento_solo_pisa_campos_enviados` (`:99-119`), que cambia
  `prioridad`, no `estado`. Como `actualizar_evento` trata `estado` igual que cualquier
  otro campo del diff genérico (`service.py:118-136`), cancelar un evento **sí** queda
  auditado por la vía genérica de `registrar_cambios` (`tipo_cambio="estado"` porque
  `campo == "estado"`, `core/audit.py:55`) — no necesita un camino especial como
  `completar_evento`. Ver [`estados.md`](./estados.md).
