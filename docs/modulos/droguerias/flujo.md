# Flujos — Droguerías

Los 3 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en esta
sesión.

## Flujo 1 — Alta de droguería (`POST /droguerias`)

1. El router exige `require_roles("superadmin")` (`router.py:41`).
2. `crear_drogueria_endpoint` llama a `crear_drogueria_para_endpoint(body=body)`
   (`router.py:43`).
3. `crear_drogueria_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_drogueria` (`service.py:41-42`).
4. `crear_drogueria` valida el body con Pydantic (incluyendo RN-DROGUERIAS-001, formato
   de CUIT) y hace `repo.crear_drogueria(client, body.model_dump())` — sin
   validaciones adicionales de negocio, sin chequeo de duplicados de `cuit`
   (`service.py:12-13`).
5. `repo.crear_drogueria` hace el INSERT y devuelve la fila creada
   (`repository.py:11-12`).
6. El endpoint responde con `DrogueriaOut` (`router.py:39`,
   `response_model=DrogueriaOut`).

No hay validación de unicidad de `cuit` en este flujo: dos droguerías podrían crearse
con el mismo CUIT sin que este módulo lo impida — no se pudo confirmar si existe una
constraint `UNIQUE` a nivel de columna en la base (no verificable desde este código).
Pendiente de definición funcional — ver [`pendientes.md`](./pendientes.md).

## Flujo 2 — Edición de droguería (`PATCH /droguerias/{id}`), incluida asignación de plan

1. El router exige `require_roles("superadmin")` (`router.py:50`).
2. `actualizar_drogueria_endpoint` llama a
   `actualizar_drogueria_para_endpoint(drogueria_id=drogueria_id, body=body)`
   (`router.py:52`).
3. `actualizar_drogueria_para_endpoint` resuelve `get_service_client()` y delega en
   `actualizar_drogueria` (`service.py:45-46`).
4. `actualizar_drogueria` valida existencia con `repo.obtener_drogueria`
   (RN-DROGUERIAS-002, `service.py:19-21`) — `NotFoundError` si no hay fila.
5. Arma `campos = body.model_dump(exclude_unset=True)` (RN-DROGUERIAS-003,
   `service.py:23`) — si el body solo trae `plan_id`, solo ese campo se pisa; el resto
   de la fila (incluido `activa`, `nombre`, etc.) queda intacto.
6. `repo.actualizar_drogueria` hace el UPDATE (`service.py:24`, `repository.py:15-16`).
7. El endpoint responde con `DrogueriaOut` (`router.py:46`).

Este es el único flujo por el que una droguería queda asociada a un plan: no hay un
endpoint separado de "asignar plan" — se envía `plan_id` como cualquier otro campo del
`PATCH` genérico. No hay validación de que el `plan_id` enviado exista o esté activo
en `service.py` (la integridad la garantiza únicamente la FK de Postgres, que
rechazaría un `plan_id` inexistente con un error no traducido explícitamente por este
módulo — solo el `DELETE` traduce `APIError` a `ConflictError`, ver
RN-DROGUERIAS-004). Pendiente de definición funcional.

## Flujo 3 — Baja de droguería (`DELETE /droguerias/{id}`)

1. El router exige `require_roles("superadmin")` (`router.py:58`).
2. `eliminar_drogueria_endpoint` llama a
   `eliminar_drogueria_para_endpoint(drogueria_id=drogueria_id)` (`router.py:60`).
3. `eliminar_drogueria_para_endpoint` resuelve `get_service_client()` y delega en
   `eliminar_drogueria` (`service.py:49-50`).
4. `eliminar_drogueria` valida existencia con `repo.obtener_drogueria`
   (RN-DROGUERIAS-002, `service.py:28-30`) — `NotFoundError` si no hay fila.
5. Intenta `repo.eliminar_drogueria` — `DELETE` real, no soft-delete
   (`service.py:33`, `repository.py:19-20`).
6. Si Postgres rechaza el `DELETE` por una FK de alguna de las 36 tablas que referencian
   `drogueria_id` (usuarios, clientes, procesos comerciales, etc.), `service.py` atrapa
   `postgrest.exceptions.APIError` y levanta `ConflictError` con mensaje explícito
   (RN-DROGUERIAS-004, `service.py:34-38`).
7. El endpoint responde `204 No Content` si tuvo éxito (`router.py:55`,
   `status_code=204`), o 409 con el mensaje de `ConflictError` si había datos
   asociados.

En la práctica, dado que 36 tablas del schema referencian `drogueria_id` (ver
[`arquitectura.md`](./arquitectura.md)), es esperable que este `DELETE` falle con
`ConflictError` para casi cualquier droguería que haya tenido actividad real — el
camino "feliz" de este flujo aplica sobre todo a droguerías creadas por error, sin
datos cargados todavía.
