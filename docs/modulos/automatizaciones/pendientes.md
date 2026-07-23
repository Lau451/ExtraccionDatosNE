# Pendientes — Auditoría técnica de Automatizaciones

Clasificación P1 (ausencia de una capacidad esperada / riesgo estructural) / P2 (deuda
técnica relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión. Este módulo concentra el **hallazgo más relevante de toda la serie documentada
hasta ahora**: un motor de reglas completo, testeado, y sin ningún disparador real.

## P1 — Riesgo estructural

1. **Todo el motor (`disparar_reglas` + `procesar_acciones_pendientes`) está completo,
   testeado, y sin ningún disparador real en producción.** [IMPLEMENTADO], confirmado
   por cita textual del propio equipo dentro del código —
   `service.py:148-154` (docstring de `disparar_reglas`):

   > "Nota de alcance: esta función y `procesar_acciones_pendientes()` están completas y
   > testeadas, pero HOY nada en el código las llama fuera de los tests -- ningún flujo
   > de negocio (confirmar una OC, adjudicar una licitación, etc.) dispara
   > `disparar_reglas()`, y no existe un worker/cron real que corra
   > `procesar_acciones_pendientes()` ni el scheduler de
   > `eventos.generar_instancias_recurrentes()` periódicamente. Es exactamente el "motor
   > mínimo, sin conectar a los eventos de negocio todavía" que pedía el spec para esta
   > ronda -- conectarlo es la próxima ronda, no una omisión de esta."

   Confirmado de forma independiente por `Grep` exhaustivo de
   `disparar_reglas|procesar_acciones_pendientes` sobre todo el repositorio en esta
   sesión: los únicos call sites fuera de la propia declaración en `service.py` son
   `tests/automatizaciones/test_service.py` (7 tests que llaman a una u otra) y menciones
   en texto de documentación (`services/presupuestacion/ROADMAP.md:53-62`,
   `docs/modulos/eventos/README.md:41`). Ningún `router.py` de ningún módulo de negocio
   importa estas funciones; no existe ningún cron/worker/`Celery`/`APScheduler` en el
   repositorio (confirmado también del lado de `eventos/pendientes.md` P1(1), que hizo el
   mismo `Grep` de infraestructura de scheduling con resultado negativo). **Es un P1 más
   severo que el de `eventos/`**: en `eventos/` solo la recurrencia queda inerte (los
   eventos puntuales sí se crean/completan normalmente vía CRUD manual); acá **el módulo
   entero** —evaluación de reglas, ejecución inmediata, encolado, reintentos con
   backoff— es inalcanzable en producción salvo invocación manual, porque no hay ningún
   camino HTTP ni de negocio que llegue a `disparar_reglas`. El único uso real hoy es
   administrar reglas por CRUD (crear, listar, actualizar, ver métricas) sin que jamás se
   evalúen. Ver [`README.md`](./README.md), RN-AUTOMATIZACIONES-006 y
   `services/presupuestacion/ROADMAP.md:53-62` para el plan declarado de "conectarlo en
   la próxima ronda".

2. **`COLUMNA_FK_POR_ENTIDAD` no cubre 2 de las 7 `entidad_objetivo` admitidas por
   `reglas_automatizacion`, y el gap causa que reglas válidas se descarten en
   silencio.** [IMPLEMENTADO] (RN-AUTOMATIZACIONES-002, `repository.py:9-15`,
   `service.py:162-169`). El `Literal` `EntidadObjetivo` (`models.py:6-9`) y el `CHECK
   ck_ra_entidad` (`extractor_final.sql:889-892`) admiten 7 valores; el `CHECK
   ck_ae_una_entidad` de `acciones_ejecutadas` (`:933-939`) solo cubre 5 columnas FK.
   Un administrador puede crear hoy, sin ningún error de validación, una regla con
   `entidad_objetivo="extraction_result"` o `"entidad_objetivo="entrega"` — la BD la
   acepta (`ck_ra_entidad` la permite) y Pydantic también (`EntidadObjetivo` la incluye).
   Si algún día se conecta un disparador real para esas 2 entidades, la regla
   **matchearía silenciosamente sin ejecutar nada**: `disparar_reglas` la descarta con
   un `logger.warning` (`service.py:164-168`), sin crear fila en `acciones_ejecutadas`,
   sin lanzar excepción, sin ningún rastro visible para el usuario que la creó vía
   `POST /automatizaciones/reglas`. No hay ningún test que ejercite este caso — los 8
   tests de `test_service.py` usan exclusivamente `entidad_objetivo="proceso_comercial"`.
   Ver [`base_de_datos.md`](./base_de_datos.md).

3. **Solo 2 de los 8 `tipo_accion` posibles tienen implementación real.**
   [IMPLEMENTADO] (RN-AUTOMATIZACIONES-001, `service.py:87-131`). `crear_oc`,
   `enviar_email`, `enviar_whatsapp`, `ejecutar_agente_ia`, `cambiar_estado` y `webhook`
   —6 de los 8 valores del `Literal` `TipoAccion`— caen todos en el mismo fallback
   genérico `return False, f"tipo_accion '{tipo_accion}' no implementado aún"`
   (`:131`). Una regla creada con cualquiera de estos 6 tipos pasa toda la validación de
   creación sin ningún error, y solo falla en tiempo de ejecución — que, combinado con el
   punto 1 de este documento, en la práctica **nunca ocurre**, porque nada dispara el
   motor. El resultado combinado de los puntos 1+2+3: hoy es posible crear, vía HTTP, una
   regla sintácticamente perfecta que jamás podría producir ningún efecto (por tipo de
   acción no implementado, por entidad sin columna FK, o simplemente porque nada la
   evalúa nunca) sin que el sistema le devuelva ninguna advertencia al usuario que la
   creó. Ver [`decisiones.md`](./decisiones.md) D-AUTOMATIZACIONES-001.

## P2 — Deuda técnica relevante

1. **Desactivar una regla (`PATCH activa=false`) no cancela ni filtra las acciones ya
   encoladas que le pertenecen.** [IMPLEMENTADO], confirmado por lectura completa de
   `procesar_acciones_pendientes` y `listar_acciones_pendientes`
   (`repository.py:64-73`): el `SELECT` de pendientes no hace ningún `JOIN` ni filtro
   contra `reglas_automatizacion.activa`. Una acción `estado="pendiente"` cuya regla se
   desactivó después de encolarse se sigue ejecutando igual en la próxima corrida del
   worker (si alguna vez hay una — ver P1(1)). No hay ningún endpoint ni función para
   cancelar una acción encolada individualmente; el estado `"cancelada"` del `CHECK` de
   BD nunca se usa (ver [`estados.md`](./estados.md)). Ver también P1(1) — hoy es un
   riesgo teórico porque no hay worker real, pero se activaría el día que se conecte uno.

2. **`_ACCIONES_INMEDIATAS_SOPORTADAS` es una constante declarada y nunca usada.**
   [IMPLEMENTADO] (D-AUTOMATIZACIONES-004, `service.py:20`), confirmado por `Grep`
   exhaustivo sin más coincidencias que su propia declaración. No afecta el
   comportamiento actual (las ramas `if`/`elif` de `_ejecutar_accion` son la fuente de
   verdad real), pero es una fuente potencial de inconsistencia si en el futuro se
   agrega un tipo de acción a un lugar sin actualizar el otro.

3. **Un cambio de `parametros_accion`/`condicion` vía `PATCH` afecta retroactivamente
   acciones ya encoladas (`estado="pendiente"`) de esa regla.** [IMPLEMENTADO],
   confirmado por lectura de `procesar_acciones_pendientes` (`service.py:217`,
   `obtener_regla` trae la fila viva de la regla al momento de procesar, no una copia
   congelada al momento de encolar). Coherente con D-AUTOMATIZACIONES-002 (sin
   versionado de reglas, deliberado según el comentario de BD). No hay ningún test que
   cubra este escenario (editar una regla entre el encolado y el procesamiento de una
   acción pendiente).

4. **Ninguna validación de rango a nivel de aplicación para `max_reintentos` (0-10) ni
   `prioridad` (>=0) — solo el `CHECK` de BD los limita.** [IMPLEMENTADO],
   `models.py:26-27` (`ReglaAutomatizacionCreate`) declara ambos campos como `int` sin
   `Field(ge=..., le=...)`. Un `POST /automatizaciones/reglas` con `max_reintentos=999`
   pasa la validación de FastAPI/Pydantic y falla recién contra el `CHECK ck_ra_reintentos`
   de Supabase, devolviendo previsiblemente un error de constraint de BD en vez de un
   `422` claro y específico de la aplicación. No verificado en esta sesión el mensaje de
   error exacto que Supabase devuelve en ese caso (fuera del alcance leído).

5. **`evento_disparador` es texto libre, sin vocabulario cerrado ni validación contra
   los eventos de negocio reales del sistema.** [IMPLEMENTADO], `models.py:20`
   (`evento_disparador: str`, sin `Literal`). Un typo al crear una regla (por ejemplo
   `"completadO"` en vez de `"completado"`) produce una regla que nunca matchea nada,
   sin ningún error ni advertencia — sería indistinguible de una regla correctamente
   configurada hasta que (si algún día hay un disparador real, ver P1(1)) nunca se
   dispare. No hay ningún catálogo de valores válidos de `evento_disparador` en el
   código ni en el schema leído en esta sesión.

## P3 — Menor

1. **(Resuelto)** Se había detectado una discrepancia de nombre de función entre la
   documentación de `eventos/` (que citaba `_ejecutar_accion_inmediata`) y el código
   real de `automatizaciones/service.py:87-131` (`_ejecutar_accion`, sin sufijo, usada
   tanto para modo `inmediato` como `cola`). Corregido en `docs/modulos/eventos/{README,
   casos_de_uso,arquitectura}.md` en esta misma sesión de documentación. Ver
   [`arquitectura.md`](./arquitectura.md).

2. **`procesar_acciones_pendientes` devuelve un conteo de filas tocadas
   (`procesadas`), no de éxitos.** [IMPLEMENTADO], `service.py:265`
   (`procesadas += 1` se ejecuta en todas las ramas del `for`, incluida la de regla
   inexistente y la de reintento reprogramado). Un caller que interprete el valor de
   retorno como "cantidad de acciones completadas con éxito" leería mal el resultado —
   riesgo bajo porque hoy no hay ningún caller real (P1(1)).

3. **`estado="ejecutando"` y `estado="cancelada"` son valores válidos del `CHECK` de BD
   que ningún código de la aplicación escribe jamás.** [IMPLEMENTADO], confirmado por
   `Grep` de `"ejecutando"` y `"cancelada"` sobre `services/` y `tests/` completos en
   esta sesión, sin resultados. No representan un riesgo funcional hoy (nadie los
   necesita), pero son superficie de schema sin uso — igual patrón que `"en_progreso"`/
   `"vencido"` en `eventos/estados.md`. Ver [`estados.md`](./estados.md).

## Nota sobre el hallazgo cruzado con `notificaciones/`

`automatizaciones/service.py:16` importa `crear_notificacion` de
`services/presupuestacion/notificaciones/service.py:11-24`. Ese módulo **todavía no
tiene documentación propia** en `docs/modulos/` a la fecha de esta sesión — se
documentará completo como el siguiente módulo de esta serie. El hallazgo relevante que
ya se puede adelantar desde acá (confirmado por lectura de
`services/presupuestacion/ROADMAP.md:66-72` en esta sesión): las notificaciones creadas
por este módulo (`enviar_notificacion`) quedan con
`notificacion_entregas.estado='pendiente'` indefinidamente porque, según el propio
ROADMAP, "Falta la integración con un proveedor real de envío (...) toda entrega queda
en `notificacion_entregas.estado='pendiente'` para siempre" — un segundo motor sin
disparador de despacho real, análogo al de este módulo. Se deja constancia acá sin
documentarlo a fondo, tal como fue indicado para este alcance.
