# API pública — Notificaciones

Funciones exportadas por archivo, con firma y una línea de propósito. No incluye
funciones "privadas" salvo cuando son el único punto de una regla de negocio citada en
[`reglas.md`](./reglas.md).

## `models.py`

| Símbolo | Tipo | Descripción |
|---|---|---|
| `TipoNotificacion` | `Literal`, 13 valores | Vocabulario de `notificaciones.tipo`, igual al `CHECK ck_notif_tipo` de BD. |
| `Prioridad` | `Literal`, 4 valores | `baja, media, alta, urgente`. |
| `OrigenNotificacion` | `Literal`, 6 valores | `usuario, ia, automatizacion, webhook, api, sistema`. |
| `Canal` | `Literal`, 6 valores | `web, email, whatsapp, sms, push, webhook`. |
| `CANALES_DEFAULT` | `tuple[Canal, ...]` | `("web",)` — default cuando no hay preferencia cargada (RN-NOTIFICACIONES-002). |
| `NotificacionOut` | `BaseModel` | Response model de `GET /notificaciones/no-leidas`. No incluye las FKs polimórficas, `accion_ejecutada_id` ni `metadata` — ver [`base_de_datos.md`](./base_de_datos.md). |
| `NotificacionPreferenciaUpsert` | `BaseModel` | Body de `PUT /notificacion-preferencias`: `tipo`, `canal`, `habilitada: bool = True`. |
| `NotificacionPreferenciaOut` | `BaseModel` | Response model de preferencias. |

## `repository.py`

| Función | Firma | Descripción |
|---|---|---|
| `crear_notificacion` | `(client, fila: dict) -> dict` | `INSERT notificaciones`, devuelve la fila creada. |
| `crear_entrega` | `(client, fila: dict) -> dict` | `INSERT notificacion_entregas`, devuelve la fila creada. |
| `preferencias_de_tipo` | `(client, *, usuario_id, tipo) -> list[dict]` | `SELECT notificacion_preferencias` filtrado por usuario+tipo. |
| `obtener_notificacion` | `(client, *, notificacion_id) -> dict \| None` | `SELECT` por id, `None` si no existe. |
| `listar_no_leidas` | `(client, *, destinatario_id) -> list[dict]` | `SELECT` no leídas ni archivadas, orden `created_at desc`. |
| `marcar_leida` | `(client, *, notificacion_id) -> dict` | `UPDATE leida_at = now()`. |
| `marcar_archivada` | `(client, *, notificacion_id) -> dict` | `UPDATE archivada_at = now()`. |
| `upsert_preferencia` | `(client, fila: dict) -> dict` | `UPSERT` con `on_conflict="usuario_id,tipo,canal"`. |
| `listar_preferencias` | `(client, *, usuario_id) -> list[dict]` | `SELECT` todas las preferencias de un usuario. |

## `service.py`

| Función | Firma | Descripción |
|---|---|---|
| `crear_notificacion` | `(client, *, drogueria_id, destinatario_id, tipo, titulo, mensaje=None, prioridad="media", url_destino=None, origen="sistema", relaciones=None, metadata=None) -> dict` | **Uso interno** (RN-NOTIFICACIONES-001). Crea la notificación + entregas multi-canal. |
| `listar_no_leidas` | `(client, *, destinatario_id) -> list[dict]` | Wrapper directo de `repo.listar_no_leidas`. |
| `marcar_leida` | `(client, *, notificacion_id, usuario_id) -> dict` | Valida existencia + pertenencia (`ForbiddenError`/`NotFoundError`), delega en `repo.marcar_leida`. |
| `marcar_archivada` | `(client, *, notificacion_id, usuario_id) -> dict` | Ídem, para archivado. |
| `upsert_preferencia` | `(client, *, usuario_id, drogueria_id, body: NotificacionPreferenciaUpsert) -> dict` | Arma la fila con identidad del usuario autenticado, delega en `repo.upsert_preferencia`. |
| `listar_preferencias` | `(client, *, usuario_id) -> list[dict]` | Wrapper directo de `repo.listar_preferencias`. |
| `marcar_leida_para_endpoint` | `(*, notificacion_id, usuario_id) -> dict` | Resuelve `get_service_client()` y delega en `marcar_leida`. |
| `marcar_archivada_para_endpoint` | `(*, notificacion_id, usuario_id) -> dict` | Resuelve `get_service_client()` y delega en `marcar_archivada`. |

## `router.py`

| Endpoint | Función | `response_model` |
|---|---|---|
| `GET /notificaciones/no-leidas` | `listar_no_leidas_endpoint` | `list[NotificacionOut]` |
| `PATCH /notificaciones/{notificacion_id}/leer` | `marcar_leida_endpoint` | `NotificacionOut` |
| `PATCH /notificaciones/{notificacion_id}/archivar` | `marcar_archivada_endpoint` | `NotificacionOut` |
| `GET /notificacion-preferencias` | `listar_preferencias_endpoint` | `list[NotificacionPreferenciaOut]` |
| `PUT /notificacion-preferencias` | `upsert_preferencia_endpoint` | `NotificacionPreferenciaOut` |

Detalle completo de roles/clientes en [`casos_de_uso.md`](./casos_de_uso.md).
