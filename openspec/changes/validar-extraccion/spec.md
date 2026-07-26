# Specification: Validar extracción

## Archivos

| Archivo | Estado |
|---|---|
| `services/presupuestacion/extraccion/models.py` | Modificado — `ValidarExtraccionRequest.filas` opcional, tipado por `document_type`; nuevos modelos de listado/lectura de filas |
| `services/presupuestacion/extraccion/service.py` | Modificado — materializar desde `filas` si vienen; notificación de reemplazo vía `notificaciones/service.py` |
| `services/presupuestacion/extraccion/repository.py` | Modificado — queries de listado y lectura de filas |
| `services/presupuestacion/extraccion/router.py` | Modificado — `GET /extracciones`, `GET /extracciones/{id}/filas` nuevos; `POST .../validar` sin cambio de firma HTTP |
| `frontend/src/features/validar-extraccion/` | Nuevo — pantalla completa, recibe `NuevaLiciCotiDialog.tsx` desde `carga-documentos` |
| `frontend/src/lib/api/presupuestacion.ts` | Modificado — funciones de listado, filas y validar (con `filas` opcional) |
| `frontend/src/features/shell/Sidebar.tsx`, `frontend/src/routes/_authenticated.validar-extraccion.tsx` | Modificado/Nuevo — entrada de sidebar + ruta |
| `docker-compose.yml` | Modificado — `volumes:` compartido en ambos servicios + `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` en `extraccion-api` |
| `services/presupuestacion/notificaciones/service.py` | Reusado, sin cambios de firma — `crear_notificacion()` pasa a ser el único camino de notificación de reemplazo |
| `services/presupuestacion/extraccion/repository.py:crear_notificacion` | **Borrado** — el insert directo que causaba el bypass de canales queda sin callers una vez que el service llama a `notificaciones/service.py` |

## API

### `GET /extracciones` (nuevo)

- MUST vivir en `services/presupuestacion/extraccion/router.py`, no en `services/extraccion` (D1 — ese servicio no tiene auth).
- MUST usar `get_user_client()` (RLS-aware): solo devuelve `extraction_results` de la `drogueria_id` del usuario autenticado.
- MUST aceptar query param `validado: bool | None` — `None` (default) devuelve todas, `false`/`true` filtra.
- MUST devolver, por fila: `id`, `document_type`, `source_filename`, `row_count`, `status`, `validado`, `created_at`, y el proceso comercial vinculado (`proceso_comercial_id`, nombre) cuando exista.
- MUST NOT requerir ningún rol adicional a los ya exigidos por auth estándar de `presupuestacion` (misma sesión JWT que el resto del servicio).

### `GET /extracciones/{id}/filas` (nuevo)

- MUST usar `get_user_client()` y devolver 403/404 si la extracción no pertenece a la droguería del usuario (mismo chequeo que ya hace `POST .../validar` en `router.py:32-34`).
- MUST parsear `csv_disk_path` (mismo lector que `_leer_filas_csv`) y devolver las filas tipadas según `document_type`: `item`/`descripcion`/`cantidad` para `licitacion`/`cotizacion`; `renglon`/`proveedor`/`marca`/`precio` para `comparativa`.
- MUST devolver un error de dominio (`NotFoundError` o `ValidationError` explícito, NUNCA un 500 con `FileNotFoundError`) cuando `csv_disk_path` no es legible desde este contenedor (D4) — mensaje: "el archivo de la extracción no está disponible".
- MUST NOT implementar lectura de filas para `document_type == "orden_compra"` — no hay CSV materializable para ese tipo (ver Fuera de scope).

### `POST /extracciones/{id}/validar` (extendido)

- `ValidarExtraccionRequest` MUST ganar `filas: list[...] | None = None`, validado contra el `document_type` real de la extracción (tipos por rama igual que en `GET .../filas`).
- MUST seguir aceptando requests SIN `filas` (retrocompatibilidad): en ese caso materializa desde `csv_disk_path` exactamente como hoy — los 12 tests existentes de `tests/extraccion/test_service.py` NO deben requerir cambios.
- CUANDO `filas` viene seteado, MUST materializar desde ahí (editar, borrar, agregar filas respecto al CSV) y MUST NOT reescribir `csv_disk_path` en disco (D2) — el CSV crudo permanece como registro de lo que devolvió la IA.
- MUST NOT modificar `extraction_results.row_count` en ningún caso — sigue describiendo cuántas filas devolvió Gemini; `ResultadoValidarExtraccion.filas_creadas` sigue siendo la cuenta de lo confirmado por el humano.
- MUST seguir siendo una sola llamada atómica (D3): no existe un paso intermedio de "guardar edición" separado de la confirmación.
- MUST seguir rechazando `document_type == "orden_compra"` con el mismo `ValidationError` actual (`service.py:286-289`) — sin cambios de mensaje ni de comportamiento.

### Notificación de reemplazo de comparativa (D6 — corrige el mecanismo existente de RN-EXTRACCIONVALIDACION-012, no es funcionalidad nueva)

**Corrección post-design:** `RN-EXTRACCIONVALIDACION-012` ya está implementado hoy
(`_notificar_reemplazo_comparativa` en `service.py`), con tres defectos verificados contra el
schema real. D6 es un **fix**, no una notificación nueva. El texto original del proposal
(`tipo="comparativa_reemplazada"`, `relaciones={"extraction_result_id": ...}`, destinatarios
limitados a `gerencia`/`lider_comercial`) **no es válido contra el schema** — corregido acá.

- CUANDO `validar_extraccion` detecta que va a versionar/invalidar una comparativa vigente (mismo chequeo que hoy dispara `reemplazo=True`), el servicio MUST llamar a `services/presupuestacion/notificaciones/service.py:crear_notificacion()` — no más el insert directo a la tabla `notificaciones` vía `extraccion/repository.py:crear_notificacion` (bypass que hoy salta la creación de `notificacion_entregas`, así que la notificación nunca llega a ningún canal).
- MUST resolver destinatarios como los usuarios **`admin`, `gerencia` y `lider_comercial`** (superset ya existente — `admin` NO se excluye, angostarlo sería una regresión) activos (`activo = TRUE`) de la misma `drogueria_id` de la extracción, EXCLUYENDO al usuario que ejecutó la validación.
- MUST llamar `crear_notificacion()` una vez por destinatario, con `tipo="comparativa_disponible"` (`ck_notif_tipo` no admite otro valor), `origen="sistema"`, `prioridad="alta"`, `url_destino` apuntando a la comparativa nueva, `relaciones={"proceso_comercial_id": ..., "comparativa_id": ...}` (columnas reales de `notificaciones`), y `extraction_result_id` dentro de `metadata` (JSONB) — NUNCA dentro de `relaciones`, que no tiene esa columna.
- MUST ejecutarse DESPUÉS del flip de `validado = TRUE` (no antes, como hoy) y MUST estar envuelto en `try/except`: un fallo al notificar (a cualquier destinatario) NO revierte ni bloquea una validación que ya está confirmada en la base.
- MUST NOT crear ninguna notificación si no hay ningún destinatario elegible en esa droguería — ausencia de destinatarios no es un error.

## Infraestructura — volumen compartido (D4)

- `docker-compose.yml` MUST montar un volumen compartido con el mismo mount path (`C:/app/output`) en `extraccion-api` (read-write, ya lo usa hoy) y `presupuestacion-api` (read-only — D2, nunca escribe ahí).
- `extraccion-api` MUST recibir `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en su `environment:` — sin esto `get_client()` devuelve `None` en Docker y ninguna extracción se persiste (gap preexistente, mismo archivo que el fix del volumen).

## Frontend

- `features/validar-extraccion/` MUST incluir: listado de extracciones pendientes (filtro por `validado`), tabla editable por tipo de documento, selector/creación de proceso comercial reusando `NuevaLiciCotiDialog.tsx` (reubicado desde `carga-documentos`), y confirmación explícita vía `ConfirmDialog.tsx` que resuma filas modificadas/borradas/agregadas y advierta si va a reemplazar la comparativa vigente (D5).
- La tabla editable MUST bloquear la edición (sin truncar en silencio) cuando `row_count > 500`, mostrando un mensaje explícito y dejando solo "confirmar tal cual" o "rechazar" como opciones (D7).
- MUST agregar una entrada "Validar extracción" en `Sidebar.tsx` y una ruta bajo `_authenticated`.
- `cantidad` y `precio` de filas editadas MUST validarse por celda en el cliente antes de habilitar el submit, ADEMÁS de la validación de tipos que hace el backend (D5).

## Fuera de scope (verificable)

- Materialización de `orden_compra`: sigue sin implementación; `POST .../validar` sigue devolviendo el `ValidationError` actual sin cambios.
- Auditoría de edición de filas en `historial_cambios`: no se agrega en este change; el CSV crudo intacto es el mecanismo de reconstrucción.
- Deshacer una validación: `validado` sigue siendo de un solo sentido, sin endpoint de reversión.
- `PATCH /api/extraction-results/{id}` y `GET /api/documentos/{doc_id}` de `services/extraccion`: no se tocan ni se borran, solo se marcan como deprecados en docs.

## Scenarios

### Scenario: listar pendientes de validar
```
Given: existen extracciones con validado=true y validado=false en la droguería del usuario
When: GET /extracciones?validado=false
Then: 200, solo las no validadas de esa droguería
  AND ninguna extracción de otra droguería aparece (RLS vía get_user_client)
```

### Scenario: leer filas de una extracción de licitación
```
Given: una extracción document_type="licitacion" con csv_disk_path legible
When: GET /extracciones/{id}/filas
Then: 200, filas con item/descripcion/cantidad
```

### Scenario: leer filas cuando el volumen no está montado (Docker)
```
Given: csv_disk_path apunta a un path no accesible desde presupuestacion-api
When: GET /extracciones/{id}/filas
Then: error de dominio claro ("el archivo de la extracción no está disponible"),
  NUNCA un 500 con stack trace de FileNotFoundError
```

### Scenario: validar sin filas — comportamiento sin cambios (retrocompatibilidad)
```
Given: un caller de los 12 tests existentes envía solo proceso_comercial_id
When: POST /extracciones/{id}/validar
Then: materializa desde csv_disk_path exactamente como hoy — ningún test existente
  se rompe
```

### Scenario: validar con filas editadas — el CSV en disco no se toca
```
Given: el humano corrigió un precio y borró una fila en la tabla editable
When: POST /extracciones/{id}/validar con filas en el body
Then: se materializa desde filas del body
  AND csv_disk_path en disco permanece exactamente igual que antes de la request
  AND extraction_results.row_count no cambia
```

### Scenario: agregar una fila que Gemini se saltó
```
Given: filas del body tiene una fila más que el CSV original
When: POST /extracciones/{id}/validar
Then: se materializa incluyendo la fila agregada
  AND filas_creadas > row_count original
```

### Scenario: reemplazo de comparativa notifica a admin/gerencia/líder vía notificaciones/service.py, no bloquea si falla
```
Given: existe una comparativa vigente para el proceso comercial
  AND hay usuarios activos con rol admin, gerencia y/o lider_comercial en la droguería
When: POST /extracciones/{id}/validar materializa una nueva comparativa
Then: validado pasa a TRUE primero
  AND recién después se llama crear_notificacion() (notificaciones/service.py) una vez por
    destinatario, tipo="comparativa_disponible", con notificacion_entregas creada por canal
  AND el usuario que ejecutó la validación no está entre los destinatarios
  AND si crear_notificacion() falla (cualquier destinatario), validado igual queda en TRUE
  AND ningún usuario inactivo, de otro rol, ni de otra droguería recibe la notificación
```

### Scenario: reemplazo sin destinatarios — no es un error
```
Given: no hay ningún usuario admin, gerencia ni lider_comercial activo en la droguería
When: POST /extracciones/{id}/validar reemplaza la comparativa vigente
Then: 200, validado=TRUE, no se crea ninguna notificación, no hay excepción
```

### Scenario: más de 500 filas — la pantalla bloquea la edición, no trunca
```
Given: una extracción con row_count = 812
When: el usuario abre la tabla editable
Then: la edición celda por celda está bloqueada, con mensaje explícito
  AND las únicas acciones disponibles son "confirmar tal cual" o "rechazar"
  AND ninguna fila queda oculta u omitida sin que el usuario lo sepa
```

### Scenario: orden_compra sigue rechazado sin cambios
```
Given: una extracción con document_type="orden_compra" (llegó igual, bypass de UI)
When: POST /extracciones/{id}/validar
Then: ValidationError idéntico al actual (service.py:286-289)
  AND validado permanece FALSE
```

### Scenario: volumen compartido en Docker — mismo mount path
```
Given: docker-compose.yml con volumes: definido en ambos servicios, mismo mount path
When: extraccion-api escribe csv_disk_path y presupuestacion-api lo lee
Then: la lectura funciona (mismo path visible en ambos contenedores)
  AND si presupuestacion-api intenta escribir en ese volumen, falla — su mount es read-only (D2)
```
