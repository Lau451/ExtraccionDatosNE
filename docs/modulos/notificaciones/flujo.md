# Flujos — Notificaciones

## Flujo 1: `crear_notificacion` (uso interno)

```
llamador (automatizaciones/service.py:_ejecutar_accion, u otro código interno)
    │
    ▼
crear_notificacion(client, drogueria_id, destinatario_id, tipo, titulo, ...)
    │  service.py:11-62
    ▼
repo.crear_notificacion(client, {...})  ── INSERT notificaciones ──▶ fila creada, con id
    │  repository.py:7-8
    ▼
repo.preferencias_de_tipo(client, usuario_id=destinatario_id, tipo=tipo)
    │  repository.py:15-23  (SELECT notificacion_preferencias WHERE usuario_id=... AND tipo=...)
    ▼
   ¿preferencias no vacía?
    ├── SÍ → canales = [p["canal"] for p in preferencias if p["habilitada"]]
    │        (RN-NOTIFICACIONES-003 — puede resultar en 0 canales si todas están
    │        deshabilitadas: crear_notificacion no falla, simplemente no crea
    │        ninguna fila de entrega)
    └── NO → canales = list(CANALES_DEFAULT)  # ("web",) — RN-NOTIFICACIONES-002
    │
    ▼
for canal in canales:
    repo.crear_entrega(client, {notificacion_id, drogueria_id, canal, estado="pendiente"})
    │  repository.py:11-12, uno por canal
    ▼
return notificacion  # dict con la fila de notificaciones, sin las entregas
```

No hay rollback manual si el `INSERT` de una entrega falla a mitad del `for` (por
ejemplo, por un `UNIQUE (notificacion_id, canal)` violado, que en la práctica no
debería ocurrir porque `canales` no tiene duplicados) — la notificación ya quedó
creada, y las entregas previas del loop también. No verificado con un test que fuerce
ese escenario en esta sesión.

## Flujo 2: marcar leída / archivada

```
PATCH /notificaciones/{id}/leer  (o /archivar)
    │  router.py:33-44, sin Depends de cliente — el service resuelve internamente
    ▼
marcar_leida_para_endpoint(notificacion_id, usuario_id)  # service.py:106-107
    │
    ▼
marcar_leida(get_service_client(), notificacion_id, usuario_id)  # service.py:69-75
    │
    ▼
repo.obtener_notificacion(client, notificacion_id)  # repository.py:26-30
    │
    ▼
   ¿existe?
    ├── NO  → raise NotFoundError("No se encontró la notificación")
    └── SÍ  → ¿notificacion["destinatario_id"] == usuario_id?
               ├── NO  → raise ForbiddenError("Solo el destinatario puede marcarla como leída")
               └── SÍ  → repo.marcar_leida(client, notificacion_id)
                          │  repository.py:46-53
                          ▼
                          UPDATE notificaciones SET leida_at = now() WHERE id = ...
                          return fila actualizada
```

Mismo flujo para `marcar_archivada`, con `archivada_at` en vez de `leida_at`
(`repository.py:56-63`). Ambos wrappers `_para_endpoint` resuelven
`get_service_client()` — el `Depends(get_user_client)` que sí usan los otros 2
endpoints de lectura/preferencias no aparece acá (ver
[`arquitectura.md`](./arquitectura.md)).

## Flujo 3: lectura de no leídas y de preferencias (con `user_client`)

```
GET /notificaciones/no-leidas
    │  router.py:22-30 — Depends(get_user_client) inyecta el cliente autenticado
    ▼
listar_no_leidas(user_client, destinatario_id=usuario.id)  # service.py:65-66
    │
    ▼
repo.listar_no_leidas(user_client, destinatario_id=usuario.id)  # repository.py:33-43
    │  SELECT * FROM notificaciones
    │  WHERE destinatario_id = :id AND leida_at IS NULL AND archivada_at IS NULL
    │  ORDER BY created_at DESC
    ▼
return lista de NotificacionOut
```

Doble filtrado: el `.eq("destinatario_id", ...)` del `repository.py` **y** la policy
RLS `no_sel` (que ya permite `destinatario_id = auth.uid()`) filtran lo mismo por dos
caminos independientes — si uno se rompe, el otro contiene (ver
RN-NOTIFICACIONES-007). Mismo patrón exacto para `GET /notificacion-preferencias`
(`router.py:47-53` → `service.py:102-103` → `repository.py:75-82`, filtrando por
`usuario_id`).

## Flujo 4: `PUT /notificacion-preferencias` (upsert)

```
PUT /notificacion-preferencias
    │  router.py:56-66 — Depends(get_user_client)
    ▼
upsert_preferencia(user_client, usuario_id=usuario.id, drogueria_id=usuario.drogueria_id, body)
    │  service.py:87-99
    ▼
repo.upsert_preferencia(user_client, {usuario_id, drogueria_id, tipo, canal, habilitada})
    │  repository.py:66-72
    ▼
UPSERT notificacion_preferencias ON CONFLICT (usuario_id, tipo, canal) DO UPDATE
    ▼
return fila resultante (creada o actualizada)
```

`usuario_id` y `drogueria_id` se toman siempre del `UsuarioPerfil` autenticado
(`usuario.id`, `usuario.drogueria_id`) — el body del `PUT`
(`NotificacionPreferenciaUpsert`, `models.py:34-37`) solo puede especificar `tipo`,
`canal`, `habilitada`; no hay forma de que un request modifique la preferencia de otro
usuario ni de otra droguería vía este endpoint, ni siquiera antes de que RLS
intervenga (RN-NOTIFICACIONES-006).
