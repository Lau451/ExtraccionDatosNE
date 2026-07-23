# Decisiones de diseño — Notificaciones

Numeración D-NOTIFICACIONES-NNN, verificada contra el código en esta sesión.

### D-NOTIFICACIONES-001 — Modelo multi-canal completo (3 tablas, 6 canales) diseñado antes de tener integración de envío real

- **Decisión**: el schema modela notificación + entrega-por-canal + preferencia por
  usuario×tipo×canal, con 6 canales posibles (`web, email, whatsapp, sms, push,
  webhook`) y 5 estados de entrega, pero solo `web`-vía-`pendiente` tiene algún efecto
  observable hoy (RN-NOTIFICACIONES-008).
- **Motivo**: a diferencia de otros casos similares en este proyecto (ver
  D-AUTOMATIZACIONES-001, sin comentario explícito), acá el motivo **sí** está
  documentado con evidencia directa: `services/presupuestacion/ROADMAP.md:64-72`
  describe esto como pendiente deliberado, no como omisión — "El modelo está
  completo... Falta la integración con un proveedor real de envío... Necesita elegir
  proveedor(es) por canal... y un worker que tome las entregas pendientes y las
  procese, análogo al de automatizaciones." [IMPLEMENTADO] en el sentido de que la
  intención de diseño está confirmada por documento del propio repositorio, aunque el
  código de envío en sí no exista.
- **Ventajas**: cuando se implemente el envío real, no hace falta ninguna migración de
  schema — el modelo de datos (multi-canal, preferencias, entregas independientes por
  canal) ya soporta el caso completo; el frontend puede empezar a construir sobre
  `notificacion_preferencias` (opt-in por tipo/canal) desde ya, aunque el backend
  todavía no despache nada.
- **Desventajas**: un usuario puede configurar preferencias para `email`/`whatsapp`/
  `sms`/`push`/`webhook` (`PUT /notificacion-preferencias` no valida que el canal
  tenga integración real) creyendo que va a recibir avisos por esos medios, sin que
  eso ocurra nunca — no hay ningún indicador en la API de "canal disponible" vs
  "canal solo declarado en el modelo". Ver [`pendientes.md`](./pendientes.md).

### D-NOTIFICACIONES-002 — Decisión caso por caso de `user_client`/`service_client` en el router, con verificación explícita de policies

- **Decisión**: en vez de un patrón fijo por tipo de operación (como
  "lectura=`user_client`, escritura=`service_client`" en `automatizaciones/`), 3 de
  los 5 endpoints (`GET /notificaciones/no-leidas`, `GET /notificacion-preferencias`,
  `PUT /notificacion-preferencias`) usan `user_client` con un comentario que cita la
  policy RLS real verificada (`no_sel`, `np_sel`, `np_ins`/`np_upd` — ver
  [`arquitectura.md`](./arquitectura.md) para las citas completas).
- **Motivo**: los propios comentarios documentan la intención — usar `user_client`
  cuando la policy ya cubre el caso, dejando RLS como "red de contención real" además
  del filtro de aplicación, en vez de bypasear RLS por completo con `service_client`
  para operaciones donde no hace falta.
- **Ventajas**: reduce el radio de un bug de filtrado en `repository.py` — si el
  `.eq("destinatario_id", ...)` de `listar_no_leidas` se rompiera, RLS seguiría
  bloqueando datos ajenos (verificado empíricamente por
  RN-NOTIFICACIONES-007, no solo confiado en el papel). Es más seguro por diseño que
  el patrón uniforme "todo con `service_client`" de otros módulos.
- **Desventajas**: el patrón es más difícil de mantener consistente — requiere que
  cada desarrollador que agregue un endpoint nuevo vuelva a verificar la policy real
  antes de decidir, en vez de seguir una regla mecánica. La propia inconsistencia
  interna del módulo (ver D-NOTIFICACIONES-003) es evidencia de ese riesgo.

### D-NOTIFICACIONES-003 — `PATCH leer`/`archivar` usan `service_client` sin el mismo comentario de verificación que los otros 3 endpoints

- **Decisión**: `marcar_leida_endpoint`/`marcar_archivada_endpoint` (`router.py:33-44`)
  no inyectan ningún cliente vía `Depends` — delegan en wrappers
  (`marcar_leida_para_endpoint`/`marcar_archivada_para_endpoint`, `service.py:106-111`)
  que resuelven `get_service_client()` internamente, sin comentario que explique por
  qué no siguen el patrón de los otros 3 endpoints (usar `user_client` respaldado por
  la policy `no_upd`, que también permite `destinatario_id = auth.uid()`).
- **Motivo**: no documentado — "Motivo pendiente de definición funcional". [SUPOSICIÓN,
  no confirmada]: una hipótesis razonable es que estos dos endpoints se escribieron
  antes que el patrón de verificación explícita se estableciera para los otros 3, o
  que el chequeo de aplicación en `marcar_leida`/`marcar_archivada`
  (`ForbiddenError` si `destinatario_id != usuario_id`, RN-NOTIFICACIONES-005) se
  consideró suficiente sin necesidad de auditar la policy — pero eso mismo argumento
  también aplicaría a `listar_no_leidas`, que sí tiene su `.eq(...)` de aplicación y
  aun así se migró a `user_client` con comentario. No hay evidencia en el código de
  cuál de las dos hipótesis es la correcta.
- **Ventajas**: ninguna ventaja funcional identificada — el resultado observable
  (`ForbiddenError` ante un destinatario incorrecto) es el mismo que si usara
  `user_client`, porque el chequeo de aplicación ya lo cubre.
- **Desventajas**: rompe la uniformidad del propio patrón que el módulo estableció
  para sí mismo (D-NOTIFICACIONES-002) sin dejar rastro de la razón; para alguien que
  audite el módulo, la inconsistencia puede leerse como un descuido más que como una
  decisión — a diferencia de los otros 3 endpoints, donde el comentario deja claro que
  la elección fue deliberada. Ver [`pendientes.md`](./pendientes.md).

### D-NOTIFICACIONES-004 — Sin preferencia cargada, el default es únicamente `web`, no todos los canales

- **Decisión**: `CANALES_DEFAULT = ("web",)` (`models.py:16`) — un usuario que nunca
  configuró preferencias recibe solo la entrega `web`, no una por cada uno de los 6
  canales posibles.
- **Motivo**: no hay comentario explícito que justifique por qué `web` y no, por
  ejemplo, "todos los canales habilitados por defecto, opt-out en vez de opt-in".
  [SUPOSICIÓN, no confirmada]: es consistente con que `web` es el único canal con
  algún efecto real hoy (RN-NOTIFICACIONES-008) — elegir cualquier otro canal como
  default no cambiaría el comportamiento observable (ninguno se envía), así que la
  elección de `web` podría ser simplemente "el canal que sí funciona en la práctica
  (la bandeja de notificaciones del propio frontend)".
- **Ventajas**: comportamiento conservador — evita que un usuario reciba avisos por
  `email`/`whatsapp`/`sms` sin haberlo pedido explícitamente el día que esos canales
  tengan integración real; solo `web` (que no depende de ningún proveedor externo, es
  simplemente visible en la UI vía `GET /notificaciones/no-leidas`) llega por default.
- **Desventajas**: un usuario que nunca visita la sección de preferencias no puede
  enterarse nunca de una notificación urgente por otro medio, aunque esos medios
  existieran — pero esto es hoy un punto moot, dado que ningún canal fuera de `web`
  tiene efecto (RN-NOTIFICACIONES-008).

### D-NOTIFICACIONES-005 — `crear_notificacion` cita "eventos" como llamador en su docstring, pero el código real no lo respalda

- **Decisión/hallazgo**: el docstring de `crear_notificacion` (`service.py:25-28`)
  documenta la función como "de uso interno: la llaman otros módulos como efecto
  secundario (eventos, automatizaciones)", pero `eventos/service.py` no importa
  `notificaciones` en ningún punto — confirmado por lectura completa de sus imports
  (`eventos/service.py:1-12`) y por `Grep` de `notif` (case-insensitive) sobre todo
  `eventos/`, sin resultados.
- **Motivo**: no verificable — no hay forma de saber desde el código si "eventos" fue
  un consumidor planeado que nunca se conectó, un consumidor que se desconectó en un
  refactor posterior sin actualizar el comentario, o un error de redacción del
  docstring. "Motivo pendiente de definición funcional".
- **Impacto de la documentación**: es una corrección concreta al material de partida
  de esta sesión (que asumía ambos módulos como consumidores confirmados, siguiendo la
  cita de `docs/modulos/automatizaciones/README.md:78-86`, que también repite "eventos,
  automatizaciones" citando el mismo docstring sin verificar el lado de `eventos/`).
  El único consumidor Python real confirmado en todo el repositorio es
  `automatizaciones/service.py:16,115`. Ver [`casos_de_uso.md`](./casos_de_uso.md) y
  [`pendientes.md`](./pendientes.md).
