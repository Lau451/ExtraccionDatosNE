# Pendientes — Notificaciones

Auditoría técnica P1 (bloqueante/riesgo alto) / P2 (riesgo medio, corregir pronto) /
P3 (mejora, sin urgencia). Incluye también un hallazgo positivo (fortaleza de
testing) que vale la pena preservar como referencia para el resto del proyecto.

## Fortaleza — Los únicos 2 tests del proyecto que ejercitan RLS con un JWT real

`tests/notificaciones/test_service.py:139-166` y `:169-214`
(`test_rls_bloquea_lectura_de_notificaciones_ajenas_aunque_el_codigo_no_filtre` y
`test_rls_bloquea_update_de_preferencia_ajena_aunque_el_codigo_no_filtre`) usan el
fixture `crear_usuario_autenticado` (`tests/conftest.py:145-186`), que crea un usuario
real y un `Client` autenticado vía `sign_in_with_password` + `postgrest.auth(token)` —
no `service_client`, que bypasea RLS por completo. Ambos tests consultan la tabla
**sin** el filtro de aplicación que el `repository.py` real sí aplica, simulando
exactamente el escenario "el filtro de código se rompió" y confirman que la policy de
RLS (`no_sel`, `np_upd`) contiene el acceso de todas formas, y que además discrimina
por identidad (el propio dueño sí puede) en vez de bloquear todo.

El propio fixture lo documenta en su docstring (`tests/conftest.py:147-158`): "Es la
primera vez en el proyecto que se prueba RLS con un JWT real: hasta ahora todos los
tests de integración usaban `service_client`... así que ninguna policy se había
ejercitado de verdad, solo confirmado en el papel contra `pg_policies`." Confirmado
por `Grep` de `crear_usuario_autenticado` en todo el repositorio: única declaración
(`tests/conftest.py`) y único módulo que lo consume
(`tests/notificaciones/test_service.py`). `ROADMAP.md:136-146` también lo documenta
como mejora pendiente de generalizar: "valdría la pena ampliar la cobertura a
aislamiento cross-tenant explícito... La mayoría de los tests del proyecto siguen
usando `service_client` y por lo tanto no ejercitan RLS en absoluto." Este módulo es,
hasta la fecha de esta auditoría, la única excepción a esa regla — un patrón que otros
módulos podrían adoptar.

## P1 — Ninguna entrega se envía realmente por ningún canal; funcionalmente el módulo es solo un inbox interno

Confirmado exhaustivamente en esta sesión: `Grep` de librerías/SDKs de envío (`smtp`,
`sendgrid`, `twilio`, `resend`, `requests`/`httpx`/`urllib` hacia APIs externas,
`whatsapp`, `firebase`/`fcm`/`apns`, `boto3`/`ses`, `mailgun`) sobre
`services/presupuestacion/` completo, sin resultados fuera del vocabulario de
`Literal Canal`. `Grep` de `.update(` sobre `notificacion_entregas` en todo el
repositorio, sin resultados — ninguna fila de entrega transiciona nunca de
`pendiente`. Confirmado también por texto explícito del propio `ROADMAP.md:64-72`
(citado completo en [`README.md`](./README.md)).

**Impacto real**: los 6 canales del modelo (`web, email, whatsapp, sms, push,
webhook`) y las preferencias por tipo×canal existen a nivel de dato, pero solo `web`
tiene algún efecto observable (aparecer en `GET /notificaciones/no-leidas`). Un
usuario que configura `PUT /notificacion-preferencias` con `canal="email",
habilitada=True` no recibe absolutamente nada por email — la fila de entrega se crea
correctamente (RN-NOTIFICACIONES-001) pero queda `pendiente` para siempre, sin ningún
error ni aviso de que el canal no está realmente disponible.

**Recomendación** [RECOMENDACIÓN, ya presente en `ROADMAP.md:69-72`]: elegir
proveedor(es) por canal (Resend/SendGrid para email, alguna API de WhatsApp Business
para whatsapp, etc.) e implementar un worker análogo al de `automatizaciones/`
(`procesar_acciones_pendientes`) que tome filas `notificacion_entregas.estado=
'pendiente'` y las procese, actualizando `estado`/`enviado_at`/`error_msg` según
corresponda. Mientras tanto, sería razonable que `PUT /notificacion-preferencias`
rechace o marque explícitamente los canales sin integración real, para no generar
expectativas falsas en quien configura sus preferencias.

## P2 — Bypass de `extraccion_validacion/`: confirmado consistente con lo ya documentado allá

`extraccion/repository.py:101-102` sigue insertando directo contra `notificaciones`
sin pasar por `notificaciones.service.crear_notificacion`, exactamente como
documentado en
[`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)
(P2, "Bypass de `notificaciones/`"). Confirmado en esta sesión desde el lado de
`notificaciones/`: el bypass nunca genera fila en `notificacion_entregas` ni consulta
`notificacion_preferencias` — las notificaciones de reemplazo de comparativa
(`_notificar_reemplazo_comparativa`, `extraccion/service.py:112-134`) se crean incluso
si el destinatario deshabilitó explícitamente ese tipo de notificación.

Dado el hallazgo P1 de arriba (ningún canal se envía realmente hoy), el impacto
práctico inmediato de este bypass es menor de lo que sería con envío real activo — en
ambos casos (bypass o camino correcto) la notificación termina siendo solo una fila
visible en `GET /notificaciones/no-leidas`. Pero el bypass sí ignora la preferencia
del usuario de no recibir ese tipo de aviso, que es un problema independiente de si
hay envío real o no. Ver [`casos_de_uso.md`](./casos_de_uso.md) para el detalle
completo desde este lado. Recomendación ya registrada en el documento original —no se
repite acá.

## P2 — `PATCH leer`/`archivar` usan `service_client` sin el mismo comentario de verificación de policy que el resto del router

`router.py:33-44` no inyecta `user_client` ni documenta por qué, a diferencia de los
otros 3 endpoints del mismo router, que sí citan la policy RLS verificada
(`no_sel`, `np_sel`, `np_ins`/`np_upd`). El resultado observable no cambia (el chequeo
de aplicación en `marcar_leida`/`marcar_archivada` ya previene el cruce de
destinatario), pero rompe la consistencia interna del patrón "verificar policy antes
de decidir cliente" que el propio módulo estableció para sí. Ver
[`decisiones.md`](./decisiones.md) D-NOTIFICACIONES-003. Motivo pendiente de
definición funcional.

**Recomendación** [RECOMENDACIÓN]: si la policy `no_upd` (`destinatario_id =
auth.uid() OR es_superadmin()`) sigue vigente sin cambios, migrar estos 2 endpoints a
`user_client` con el mismo estilo de comentario que los otros 3, por consistencia y
para obtener la misma "red de contención real" de RLS que ya tienen `listar_no_leidas`
y las preferencias.

## P2 — Docstring de `crear_notificacion` menciona "eventos" como consumidor, pero el código no lo respalda

`service.py:25-28` documenta la función como usada por "eventos, automatizaciones",
pero `eventos/service.py` no importa ni llama a `notificaciones` en ningún punto —
confirmado por lectura completa de sus imports y `Grep` de `notif` sobre todo
`eventos/`. El único consumidor Python real confirmado es `automatizaciones/
service.py:16,115`. Ver [`decisiones.md`](./decisiones.md) D-NOTIFICACIONES-005.

**Recomendación** [RECOMENDACIÓN]: corregir el docstring para reflejar el estado real
("la llama `automatizaciones` como efecto secundario") o, si "eventos" como
consumidor fue intención de diseño, conectar `eventos/service.py` a
`crear_notificacion` para que la documentación en código vuelva a ser precisa.

## P3 — Columnas de `notificacion_entregas`/`notificaciones` que ningún código escribe jamás

`notificacion_entregas.destino`, `proveedor_externo`, `referencia_externa`,
`enviado_at`, `error_msg` (más allá del default `intentos=0`) y
`notificaciones.accion_ejecutada_id` existen en el schema pero ningún código Python
del repositorio los escribe — confirmado por `Grep` exhaustivo de cada nombre de
columna en `services/presupuestacion/`. Mismo patrón que los valores muertos
`ejecutando`/`cancelada` de `acciones_ejecutadas.estado` en `automatizaciones/`
(`docs/modulos/automatizaciones/estados.md`). No bloquea nada del uso actual —
quedarán vivos naturalmente el día que se implemente el worker de envío real (P1).

## P3 — `metadata` se acepta al crear pero nunca se expone en las respuestas

`crear_notificacion` acepta y guarda `metadata: dict | None` (`service.py:23`, `:40`),
pero `NotificacionOut` (`models.py:19-31`) no incluye ese campo — ni `metadata` ni
ninguna de las 5 FKs polimórficas ni `accion_ejecutada_id` se devuelven en `GET
/notificaciones/no-leidas`. Motivo pendiente de definición funcional: no hay
comentario que indique si es deliberado (ocultar detalles internos al frontend) o una
omisión del modelo de respuesta.

## P3 — `notificacion_preferencias.tipo` no tiene `CHECK` de vocabulario a nivel de BD

A diferencia de `notificaciones.tipo` (`ck_notif_tipo`, 13 valores), la tabla de
preferencias no tiene un `CHECK` equivalente sobre su propia columna `tipo` — la
validación de los 13 valores de `TipoNotificacion` ocurre solo a nivel de Pydantic
(`NotificacionPreferenciaUpsert.tipo`, `models.py:35`). Un `INSERT`/`UPSERT` directo a
la tabla (por ejemplo, vía `service_client` desde otro módulo, sin pasar por este
`service.py`) podría guardar un `tipo` que no corresponde a ningún valor real de
`notificaciones.tipo`, sin que la BD lo rechace. Riesgo teórico, no observado en
ningún call site actual — confirmado que todos los escritores de
`notificacion_preferencias` pasan por `NotificacionPreferenciaUpsert`.
