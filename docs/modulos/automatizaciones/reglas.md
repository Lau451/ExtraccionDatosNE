# Reglas — Automatizaciones

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`, `models.py`) y sus tests (`tests/automatizaciones/test_service.py`) en
esta sesión.

### RN-AUTOMATIZACIONES-001 — Solo 2 de los 8 `tipo_accion` posibles están implementados

- **Descripción**: `TipoAccion` (`models.py:10-13`) declara 8 valores: `crear_evento`,
  `crear_oc`, `enviar_notificacion`, `enviar_email`, `enviar_whatsapp`,
  `ejecutar_agente_ia`, `cambiar_estado`, `webhook`. `_ejecutar_accion`
  (`service.py:87-131`) solo tiene una rama `if` real para `crear_evento` (`:99-110`) y
  `enviar_notificacion` (`:112-129`).
- **Condición**: `regla["tipo_accion"]` no coincide con `"crear_evento"` ni
  `"enviar_notificacion"`.
- **Resultado**: `return False, f"tipo_accion '{regla['tipo_accion']}' no implementado
  aún"` (`service.py:131`) — la acción nunca se ejecuta, y el mensaje de error queda
  literal en `error_msg`/`resultado` de `acciones_ejecutadas`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:87-131`.
- **Observaciones**: [IMPLEMENTADO]. Verificado también desde el otro lado: la constante
  `_ACCIONES_INMEDIATAS_SOPORTADAS = {"crear_evento", "enviar_notificacion"}`
  (`service.py:20`) enumera exactamente los mismos 2 valores, pero **no se referencia en
  ningún otro punto del archivo** — confirmado por `Grep` de
  `_ACCIONES_INMEDIATAS_SOPORTADAS` en todo el repositorio, única coincidencia en su
  propia declaración. `_ejecutar_accion` usa `if`/`elif` explícitos sobre
  `regla["tipo_accion"]` en vez de comprobar pertenencia a este set — la constante es un
  artefacto sin uso, no una guarda real (ver [`decisiones.md`](./decisiones.md)).
  Cubierto por tests: `test_procesar_acciones_pendientes_reintenta_con_backoff_si_falla`
  (`test_service.py:159-183`) y
  `test_procesar_acciones_pendientes_marca_fallida_al_agotar_reintentos`
  (`:186-216`) usan `tipo_accion="enviar_email"` deliberadamente para ejercitar el
  camino "no implementado" y su interacción con los reintentos — no hay ningún test que
  cubra `crear_oc`, `enviar_whatsapp`, `ejecutar_agente_ia`, `cambiar_estado` ni
  `webhook` específicamente, pero los 5 comparten el mismo fallback genérico así que el
  comportamiento es idéntico al de `enviar_email` verificado.

### RN-AUTOMATIZACIONES-002 — Una regla con `entidad_objetivo` sin columna FK se omite en silencio (con log)

- **Descripción**: si `COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)` devuelve `None`
  (caso `extraction_result`/`entrega`), la regla que matcheó `entidad_objetivo` +
  `evento_disparador` + `condicion` **no se ejecuta ni se encola** — se descarta con un
  `logger.warning`.
- **Condición**: `entidad_objetivo in ("extraction_result", "entrega")` para una regla
  activa que matchea el disparo.
- **Resultado**: `continue` sin crear fila en `acciones_ejecutadas`
  (`service.py:162-169`) — a diferencia del camino de "tipo_accion no implementado"
  (RN-AUTOMATIZACIONES-001), que sí deja una fila con `estado='fallida'`/`'pendiente'`
  para que quede rastro, este caso no deja ningún rastro en la tabla, solo en el log de
  aplicación.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:156-169`
  (`disparar_reglas`).
- **Observaciones**: [IMPLEMENTADO]. Ver detalle de la causa raíz (gap de schema) en
  [`base_de_datos.md`](./base_de_datos.md). Sin cobertura de test — ver
  RN-AUTOMATIZACIONES-001.

### RN-AUTOMATIZACIONES-003 — `condicion=None` es comodín; el único formato soportado es igualdad exacta de un campo

- **Descripción**: `_evaluar_condicion(condicion, datos)` devuelve `True`
  incondicionalmente si `condicion` es `None` o un dict vacío/falsy; si tiene contenido,
  solo compara `datos.get(condicion["campo"]) == condicion["valor"]`.
- **Condición**: cualquier llamada a `disparar_reglas`.
- **Resultado**: reglas sin `condicion` se ejecutan siempre que matcheen
  `entidad_objetivo`+`evento_disparador`; reglas con `condicion` solo si el campo
  indicado tiene exactamente ese valor en `datos`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:77-84`.
- **Observaciones**: [IMPLEMENTADO]. Cita textual del docstring (`:78-79`): "condicion=None
  es comodín (siempre matchea). Formato soportado (deliberadamente simple, según el
  spec): {"campo": "...", "valor": ...} → datos.get(campo) == valor." No hay soporte
  para múltiples condiciones, operadores relacionales, ni acceso a campos anidados —
  confirmado por lectura completa de la función (8 líneas). Verificado por
  `test_disparar_reglas_condicion_no_matchea_no_ejecuta` (`test_service.py:58-72`).

### RN-AUTOMATIZACIONES-004 — `modo_ejecucion` determina ejecución sincrónica vs encolada, sin excepción

- **Descripción**: toda regla que matchea entidad+evento+condición se resuelve por su
  `modo_ejecucion`: `"inmediato"` ejecuta `_ejecutar_accion` sincrónicamente dentro de
  `disparar_reglas` y guarda el resultado ya resuelto; `"cola"` inserta una fila
  `estado="pendiente"` sin ejecutar nada todavía.
- **Condición**: `regla["modo_ejecucion"] == "inmediato"` vs cualquier otro valor
  (en la práctica, solo `"cola"`, por el `CHECK ck_ra_modo`).
- **Resultado**: ver desglose completo en [`flujo.md`](./flujo.md).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:171-205`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_disparar_reglas_modo_inmediato_crea_evento_sincronicamente`
  (`test_service.py:76-100`) y `test_disparar_reglas_modo_cola_encola_pendiente`
  (`:104-125`).

### RN-AUTOMATIZACIONES-005 — Reintentos con backoff exponencial en minutos, hasta `max_reintentos`

- **Descripción**: `procesar_acciones_pendientes` reintenta una acción fallida
  reprogramándola con `proximo_intento_at = fin + timedelta(minutes=2 ** intentos)`
  mientras `intentos < regla["max_reintentos"]`; al agotar los reintentos, la marca
  `fallida` de forma definitiva.
- **Condición**: `_ejecutar_accion` devuelve `exito=False` para una acción pendiente.
- **Resultado**:
  - `intentos < max_reintentos` → `estado="pendiente"`, `error_msg` actualizado,
    `proximo_intento_at` reprogramado (`service.py:248-256`). La secuencia de espera es
    2, 4, 8, 16... minutos según el intento (`2**intentos`, no `2**(intentos-1)`, ver
    detalle en [`flujo.md`](./flujo.md)).
  - `intentos >= max_reintentos` → `estado="fallida"` definitivo, con
    `finalizado_at` seteado (`:257-264`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:211-267`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_procesar_acciones_pendientes_reintenta_con_backoff_si_falla`
  (`test_service.py:159-183`, confirma `intentos==1` y `proximo_intento_at is not None`
  tras el primer fallo) y
  `test_procesar_acciones_pendientes_marca_fallida_al_agotar_reintentos`
  (`:186-216`, con `max_reintentos=2`, fuerza `proximo_intento_at` al pasado para
  simular que venció el backoff, y confirma `estado="fallida"` e `intentos==2` en la
  segunda pasada). No hay ningún test que verifique el valor exacto de
  `proximo_intento_at` (los 2/4/8 minutos concretos) — solo que no es `None`.

### RN-AUTOMATIZACIONES-006 — `disparar_reglas`/`procesar_acciones_pendientes` no tienen ningún disparador real

- **Descripción**: ambas funciones existen, están implementadas por completo y tienen
  tests de integración, pero ningún proceso del repositorio las invoca fuera de los
  tests.
- **Condición**: siempre — es una ausencia estructural, no condicional.
- **Resultado**: las reglas activas nunca se evalúan contra eventos de negocio reales
  (confirmar una OC, adjudicar una licitación, etc.), y las acciones que sí llegaran a
  encolarse manualmente nunca serían procesadas por un worker automático.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:134-267`.
- **Observaciones**: [IMPLEMENTADO], confirmado por cita textual del propio código
  (`:148-154`, completa en [`README.md`](./README.md)) y por `Grep` exhaustivo de
  `disparar_reglas|procesar_acciones_pendientes` en todo el repositorio: únicos call
  sites fuera de la declaración, `tests/automatizaciones/test_service.py` y menciones en
  texto de documentación/roadmap. Ver [`pendientes.md`](./pendientes.md) P1(1), el
  hallazgo más relevante de este módulo.

### RN-AUTOMATIZACIONES-007 — `actualizar_regla` solo pisa campos enviados y valida pertenencia a la droguería

- **Descripción**: `actualizar_regla` primero busca la regla por id y compara su
  `drogueria_id` contra la del usuario; si no existe o pertenece a otra droguería,
  rechaza con `NotFoundError`. Luego arma el diff con `body.model_dump(exclude_unset
  =True)`, así que un campo no enviado en el `PATCH` no se toca.
- **Condición**: cualquier `PATCH /automatizaciones/reglas/{regla_id}`.
- **Resultado**: `regla is None or regla["drogueria_id"] != drogueria_id` →
  `raise NotFoundError("No se encontró la regla")` (`service.py:52-53`); en caso
  contrario, `repo.actualizar_regla(client, regla_id=..., campos=campos)` con solo los
  campos presentes en el body más `updated_by` (`:54-56`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:48-56`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_actualizar_regla_solo_pisa_campos_enviados` (`test_service.py:40-54`): actualiza
  solo `activa`, y confirma que `prioridad` (seteada al crear con `prioridad=5`) no se
  pierde. La comparación de tenant usa `user_client`/`service_client` indistintamente
  según quien la invoque (el wrapper `actualizar_regla_para_endpoint` siempre resuelve
  `service_client`, `:70-72`) — no se verificó en esta sesión si RLS ya bloquearía este
  cruce de tenant incluso sin el chequeo explícito de `service.py:52`.

### RN-AUTOMATIZACIONES-008 — Todas las reglas activas que matchean se evalúan; no hay "detenerse en el primer match"

- **Descripción**: `disparar_reglas` itera **todas** las reglas devueltas por
  `reglas_activas_para` (ordenadas por `prioridad desc`) y ejecuta/encola una acción por
  cada una que matchee su condición — la `prioridad` solo determina el **orden** de
  ejecución, no si una regla de menor prioridad se salta cuando una de mayor prioridad
  ya matcheó.
- **Condición**: dos o más reglas activas comparten `entidad_objetivo` +
  `evento_disparador` y ambas matchean la misma `condicion` para el mismo disparo.
- **Resultado**: se generan tantas filas en `acciones_ejecutadas` como reglas matcheen,
  todas en la misma llamada a `disparar_reglas` (`service.py:155-208`, el `for regla in
  ...` no tiene ningún `break`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/automatizaciones/service.py:134-208`.
- **Observaciones**: [IMPLEMENTADO], confirmado por lectura completa del `for` — no hay
  ningún `break` ni bandera de "ya se ejecutó una acción para este disparo". No hay
  ningún test con 2+ reglas activas simultáneas para el mismo
  `entidad_objetivo`+`evento_disparador` — todos los tests de `disparar_reglas` crean
  una sola regla por test (`test_service.py:58-125`). Comportamiento inferido de código,
  no confirmado por test.
