# Reglas — Notificaciones

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`, `models.py`, `router.py`) y sus tests
(`tests/notificaciones/test_service.py`) en esta sesión.

### RN-NOTIFICACIONES-001 — `crear_notificacion` genera una fila de entrega por cada canal habilitado del destinatario para ese tipo

- **Descripción**: `crear_notificacion` (`service.py:11-62`) primero inserta la
  notificación, luego consulta `preferencias_de_tipo(usuario_id=destinatario_id,
  tipo=tipo)`. Si hay preferencias cargadas, usa los canales con `habilitada=True`; si
  no hay ninguna, usa `CANALES_DEFAULT`.
- **Condición**: cualquier llamada a `crear_notificacion`.
- **Resultado**: una fila en `notificacion_entregas` por cada canal en la lista
  resultante (`service.py:51-60`), todas con `estado="pendiente"`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/service.py:11-62`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_crear_notificacion_sin_preferencia_usa_canal_web_default`
  (`test_service.py:16-36`) y
  `test_crear_notificacion_respeta_preferencias_habilitadas` (`:39-71`).

### RN-NOTIFICACIONES-002 — Sin preferencia cargada, el default del backend es únicamente el canal `web`

- **Descripción**: `CANALES_DEFAULT: tuple[Canal, ...] = ("web",)` (`models.py:16`) —
  un usuario que nunca configuró preferencias para un `tipo` de notificación dado
  recibe **solo** una entrega por canal `web`, no una por cada uno de los 6 canales
  posibles.
- **Condición**: `preferencias_de_tipo(usuario_id, tipo)` devuelve lista vacía.
- **Resultado**: `canales = list(CANALES_DEFAULT)` (`service.py:49`) → una única fila
  de entrega con `canal="web"`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/models.py:16`,
  `service.py:45-49`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_crear_notificacion_sin_preferencia_usa_canal_web_default`
  (`test_service.py:16-36`, `len(entregas) == 1` y `entregas[0]["canal"] == "web"`).

### RN-NOTIFICACIONES-003 — Si hay preferencias cargadas, solo se generan entregas para los canales con `habilitada=True`

- **Descripción**: cuando `preferencias` no está vacía, `crear_notificacion` filtra
  explícitamente `[p["canal"] for p in preferencias if p["habilitada"]]`
  (`service.py:47`) — un canal con preferencia cargada pero `habilitada=False` **no**
  genera fila de entrega, y no cae al default `web` tampoco (el default solo aplica si
  la lista de preferencias está vacía, no si está poblada pero todas deshabilitadas).
- **Condición**: existe al menos una fila en `notificacion_preferencias` para ese
  `usuario_id`+`tipo`.
- **Resultado**: cero o más filas de entrega, exactamente una por canal habilitado.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/service.py:45-49`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_crear_notificacion_respeta_preferencias_habilitadas` (`test_service.py:39-71`):
  configura `web=True`/`email=False` para `tipo="oc_creada"` y confirma
  `[e["canal"] for e in entregas] == ["web"]` — solo una entrega, no dos ni cero.

### RN-NOTIFICACIONES-004 — Lectura de notificaciones no leídas, scopeada siempre al destinatario

- **Descripción**: `listar_no_leidas` (`service.py:65-66` → `repository.py:33-43`)
  filtra por `destinatario_id` exacto, `leida_at IS NULL` y `archivada_at IS NULL`,
  ordenado por `created_at desc`. Una notificación leída **o** archivada deja de
  aparecer, sin distinción entre ambos motivos en el resultado.
- **Condición**: `GET /notificaciones/no-leidas`.
- **Resultado**: lista de `NotificacionOut`, potencialmente vacía.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/repository.py:33-43`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_listar_no_leidas_excluye_leidas_y_archivadas` (`test_service.py:75-89`) y
  `test_marcar_archivada` (`:105-116`, confirma que archivar también saca de la
  lista). Doble defensa confirmada empíricamente por
  `test_rls_bloquea_lectura_de_notificaciones_ajenas_aunque_el_codigo_no_filtre`
  (`:139-166`) con un `Client` autenticado real — ver RN-NOTIFICACIONES-007.

### RN-NOTIFICACIONES-005 — Solo el propio destinatario puede marcar una notificación como leída o archivada

- **Descripción**: `marcar_leida`/`marcar_archivada` (`service.py:69-84`) obtienen la
  notificación por id y comparan `notificacion["destinatario_id"] != usuario_id`
  **antes** de aplicar el `UPDATE`.
- **Condición**: `PATCH /notificaciones/{id}/leer` o `.../archivar` para una
  notificación cuyo `destinatario_id` no coincide con el usuario autenticado.
- **Resultado**: `raise ForbiddenError(...)` (`service.py:74`, `:83`) — el `UPDATE`
  nunca se ejecuta. Si la notificación no existe, `raise NotFoundError(...)` (`:72`,
  `:81`) antes incluso de comparar destinatario.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/service.py:69-84`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_marcar_leida_de_otro_destinatario_lanza_forbidden` (`test_service.py:92-101`).
  Esta guarda es de **código de aplicación**, corre siempre con `service_client`
  (`marcar_leida_para_endpoint`, `service.py:106-107`) — no depende de la policy
  `no_upd` de RLS para funcionar, a diferencia de `listar_no_leidas`/
  `listar_preferencias`/`upsert_preferencia`, que sí se ejecutan con `user_client`.
  Ver [`arquitectura.md`](./arquitectura.md) y [`decisiones.md`](./decisiones.md)
  D-NOTIFICACIONES-003.

### RN-NOTIFICACIONES-006 — Preferencias son idempotentes por `(usuario_id, tipo, canal)`

- **Descripción**: `upsert_preferencia` (`repository.py:66-72`) usa
  `.upsert(fila, on_conflict="usuario_id,tipo,canal")`, respaldado por
  `CONSTRAINT uq_notif_pref UNIQUE (usuario_id, tipo, canal)`
  (`extractor_final.sql:1045`). Llamar dos veces con el mismo `(usuario_id, tipo,
  canal)` actualiza la misma fila (`habilitada`), no crea una segunda.
- **Condición**: `PUT /notificacion-preferencias` repetido para el mismo
  `usuario_id`+`tipo`+`canal`.
- **Resultado**: una única fila final, con el valor de `habilitada` del último
  `upsert`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/notificaciones/repository.py:66-72`.
- **Observaciones**: [IMPLEMENTADO]. Verificado por
  `test_upsert_preferencia_es_idempotente_por_usuario_tipo_canal`
  (`test_service.py:120-135`).

### RN-NOTIFICACIONES-007 — RLS es una segunda barrera real, no solo teórica, verificada con un `Client` autenticado

- **Descripción**: dos tests ejercitan las policies `no_sel`/`np_upd` de RLS
  consultando la tabla **directamente**, sin pasar por las funciones de
  `repository.py` que sí filtran por `destinatario_id`/`usuario_id` — simulando qué
  pasaría si ese filtro de aplicación se rompiera.
- **Condición**: un `Client` autenticado con JWT real (no `service_client`) intenta
  leer notificaciones ajenas o actualizar una preferencia ajena sin filtrar por
  identidad.
- **Resultado**: RLS deja pasar cero filas ajenas (`SELECT` sin `.eq("destinatario_id",
  ...)` no trae la notificación de otro usuario; `UPDATE` sin `.eq("usuario_id", ...)`
  sobre la fila de otro usuario devuelve `resultado.data == []`), y confirma además que
  la policy no bloquea todo indiscriminadamente (el propio dueño sí puede leer/editar
  su fila por el mismo camino).
- **Prioridad**: Alta (fortaleza de calidad, no un riesgo).
- **Archivo**: `tests/notificaciones/test_service.py:139-166`, `:169-214`.
- **Observaciones**: [IMPLEMENTADO]. Usa el fixture `crear_usuario_autenticado`
  (`tests/conftest.py:145-186`), que crea un usuario real y un `Client` autenticado
  con `sign_in_with_password` + `postgrest.auth(access_token)`, en vez de
  `service_client` (que bypasea RLS por completo). El propio fixture documenta en su
  docstring (`tests/conftest.py:147-158`) que es "la primera vez en el proyecto que se
  prueba RLS con un JWT real" — confirmado por `Grep` de `crear_usuario_autenticado`
  en todo el repositorio: única declaración (`tests/conftest.py`) y único módulo que
  lo usa (`tests/notificaciones/test_service.py`). Ver
  [`pendientes.md`](./pendientes.md), fortaleza destacada.

### RN-NOTIFICACIONES-008 — Ninguna entrega transiciona nunca fuera de `pendiente`

- **Descripción**: `crear_entrega` (`repository.py:11-12`) inserta siempre con
  `estado="pendiente"` (fijado en `service.py:58`, no parametrizable desde el
  llamador), y ningún otro punto del código actualiza `notificacion_entregas`.
- **Condición**: siempre — es una ausencia estructural, no condicional.
- **Resultado**: toda fila de `notificacion_entregas` queda `pendiente` para siempre;
  los valores `enviando`, `enviada`, `fallida`, `cancelada` del `CHECK ck_ne_estado`
  nunca se escriben.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/notificaciones/repository.py:11-12`,
  `service.py:51-60`.
- **Observaciones**: [IMPLEMENTADO], confirmado por `Grep` exhaustivo de librerías de
  envío (`smtp`, `sendgrid`, `twilio`, `resend`, `requests`/`httpx` hacia APIs
  externas, `whatsapp`, `firebase`/`fcm`, `boto3`/`ses`, `mailgun`) sobre
  `services/presupuestacion/` completo y de `.update(` sobre `notificacion_entregas`
  en todo el repositorio, ambos sin resultados fuera del propio vocabulario de
  `Canal`. Confirmado también por `ROADMAP.md:64-72`, citado completo en
  [`README.md`](./README.md). Ver [`estados.md`](./estados.md).
