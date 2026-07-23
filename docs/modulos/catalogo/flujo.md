# Flujos — Catálogo

Los 6 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en
esta sesión.

## Flujo 1 — Alta de producto (`POST /productos`)

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATALOGO)` — `("admin",
   "gerencia", "compras")` (`router.py:44`, `:66`).
2. `crear_producto_endpoint` llama a
   `crear_producto_para_endpoint(drogueria_id=usuario.drogueria_id, body=body,
   usuario_id=usuario.id)` (`router.py:68`).
3. `crear_producto_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_producto` (`service.py:72-73`).
4. `crear_producto` arma la fila con `drogueria_id`, todos los campos del body,
   `created_by=usuario_id` y `updated_by=usuario_id`, e inserta directo — sin
   validaciones adicionales de unicidad de `codigo_interno` en este módulo
   (`service.py:23-42`).
5. `repo.crear_producto` hace el `INSERT` y devuelve la fila creada
   (`repository.py:10-11`).
6. El endpoint responde con `ProductoOut` (`router.py:63`,
   `response_model=ProductoOut`).

No hay validación de duplicados de `codigo_interno` en este flujo — a diferencia de
`imports/repository.py`, que sí tiene un `UNIQUE(drogueria_id, codigo_interno)` para
su upsert masivo. Si dos altas por esta API usan el mismo `codigo_interno`, el
comportamiento depende de si esa constraint existe también a nivel de tabla (no
verificable solo con este código Python) — ver [`pendientes.md`](./pendientes.md).

## Flujo 2 — Edición de producto (`PATCH /productos/{id}`)

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATALOGO)` (`router.py:84`).
2. `actualizar_producto_endpoint` llama a
   `actualizar_producto_para_endpoint(producto_id=producto_id,
   drogueria_id=usuario.drogueria_id, body=body, usuario_id=usuario.id)`
   (`router.py:86-88`).
3. `actualizar_producto_para_endpoint` resuelve `get_service_client()` y delega en
   `actualizar_producto` (`service.py:76-81`).
4. `actualizar_producto` valida existencia y pertenencia con `obtener_producto`
   (RN-CATALOGO-001, `service.py:61`) — `NotFoundError` si el producto no existe o es
   de otra droguería.
5. Arma `campos = body.model_dump(exclude_unset=True)` y agrega `updated_by`
   (RN-CATALOGO-002, `service.py:62-63`).
6. `repo.actualizar_producto` hace el `UPDATE` parcial (`repository.py:42-43`).
7. El endpoint responde con `ProductoOut` (`router.py:80`).

## Flujo 3 — Gestión de categorías (`POST`/`PATCH /categorias[/{id}]`)

### Alta

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATEGORIAS)` — `("admin",
   "gerencia")`, más restrictivo que `_ROLES_ESCRITURA_CATALOGO` porque excluye
   `compras` (`router.py:45`, `:115`).
2. `crear_categoria_endpoint` llama a
   `crear_categoria_para_endpoint(drogueria_id=usuario.drogueria_id, body=body)`
   (`router.py:117`).
3. `crear_categoria_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_categoria` (`service.py:110-111`).
4. `crear_categoria` inserta directo, sin validaciones adicionales
   (`service.py:90-93`).
5. El endpoint responde con `CategoriaOut` (`router.py:112`).

### Edición

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATEGORIAS)` (`router.py:124`).
2. `actualizar_categoria_endpoint` llama a
   `actualizar_categoria_para_endpoint(categoria_id=categoria_id,
   drogueria_id=usuario.drogueria_id, body=body)` (`router.py:126-128`).
3. `actualizar_categoria_para_endpoint` resuelve `get_service_client()` y delega en
   `actualizar_categoria` (`service.py:114-117`).
4. `actualizar_categoria` valida pertenencia con `repo.obtener_categoria`
   (`service.py:103-105`) — `NotFoundError` si no existe o es de otra droguería — y
   aplica actualización parcial (RN-CATALOGO-002, `service.py:106-107`).
5. El endpoint responde con `CategoriaOut` (`router.py:120`).

No hay flujo de baja: `categorias` no tiene soft-delete ni endpoint `DELETE`
(RN-CATALOGO-004).

## Flujo 4 — Gestión de proveedores (`POST`/`PATCH`/`DELETE /proveedores[/{id}]`)

Análogo al de productos, con dos diferencias: campos propios
(`es_proveedor_compra`, `es_competidor`, `plazo_pago_dias`, `condiciones_pago`) y que
el `DELETE` usa una tupla de roles hardcodeada en vez de una constante nombrada (ver
[`decisiones.md`](./decisiones.md) sobre esta inconsistencia).

1. Alta: `router.py:145` (rol) → `crear_proveedor_endpoint`
   (`router.py:147`) → `crear_proveedor_para_endpoint` (`service.py:170-171`) →
   `crear_proveedor` arma la fila con los 8 campos propios más
   `created_by`/`updated_by` (`service.py:122-140`) → `repo.crear_proveedor`
   (`repository.py:80-81`).
2. Edición: `router.py:163` (rol) → `actualizar_proveedor_endpoint`
   (`router.py:165-167`) → `actualizar_proveedor_para_endpoint`
   (`service.py:174-179`) → `actualizar_proveedor` valida pertenencia
   (RN-CATALOGO-001, `service.py:159`) y aplica `exclude_unset`
   (RN-CATALOGO-002, `service.py:160-161`) → `repo.actualizar_proveedor`
   (`repository.py:110-111`).
3. Baja: `router.py:173` — `require_roles("admin", "gerencia")` hardcodeado, no una
   constante — → `eliminar_proveedor_endpoint` (`router.py:175-177`) →
   `eliminar_proveedor_para_endpoint` (`service.py:182-185`) → `eliminar_proveedor`
   valida pertenencia (`service.py:166`) y hace soft-delete
   (RN-CATALOGO-003, `service.py:167`, `repository.py:114-121`).

## Flujo 5 — Actualización de costo con versionado (`POST /productos/{id}/costos`)

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATALOGO)` (`router.py:194`).
2. `crear_costo_endpoint` llama a
   `crear_costo_para_endpoint(producto_id=producto_id,
   drogueria_id=usuario.drogueria_id, body=body)` (`router.py:196`).
3. `crear_costo_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_costo` (`service.py:225-226`).
4. `crear_costo` valida producto y droguería con `obtener_producto`
   (RN-CATALOGO-001, `service.py:198`).
5. Trae el costo vigente: `vigente = repo.costo_vigente(client,
   producto_id=producto_id)` (`service.py:199`).
6. Si `vigente` existe y su `costo_unitario` es igual al recibido, devuelve el
   vigente sin escribir nada (RN-CATALOGO-005, `service.py:201-202`).
7. Si `vigente` existe y el valor difiere, calcula `fecha_cierre = fecha_desde -
   1 día` y cierra el vigente (RN-CATALOGO-006, `service.py:204-206`).
8. Inserta la fila nueva con `origen="manual"` y `fecha_hasta=None`
   (RN-CATALOGO-007, `service.py:208-218`).
9. El endpoint responde con `CostoOut` (`router.py:190`).

## Flujo 6 — Ajuste manual de stock (`PATCH /productos/{id}/stock`)

1. El router exige `require_roles(*_ROLES_ESCRITURA_CATALOGO)` (`router.py:213`).
2. `ajustar_stock_endpoint` llama a
   `ajustar_stock_para_endpoint(producto_id=producto_id,
   drogueria_id=usuario.drogueria_id, body=body)` (`router.py:215`).
3. `ajustar_stock_para_endpoint` resuelve `get_service_client()` y delega en
   `ajustar_stock` (`service.py:257-258`).
4. `ajustar_stock` valida producto y droguería con `obtener_producto`
   (RN-CATALOGO-001, `service.py:241`).
5. Resuelve el depósito: el enviado en el body, o `DEPOSITO_SENTINEL` si no se
   especificó (RN-CATALOGO-009, `service.py:247`).
6. Arma la fila del upsert **solo** con `producto_id`, `drogueria_id`, `deposito` y
   `cantidad_disponible` — `cantidad_comprometida` no aparece (RN-CATALOGO-010,
   `service.py:239-240` comentario, `:244-249` dict).
7. `repo.upsert_stock` hace el upsert idempotente por `(producto_id, deposito)`
   (RN-CATALOGO-008, `repository.py:185-191`).
8. El endpoint responde con `StockOut` (`router.py:209`).

Ver [`arquitectura.md`](./arquitectura.md) para cómo este flujo convive con el motor
de compromiso de `core/stock.py`, que también escribe `cantidad_disponible` en un
flujo distinto (entrega de OC).
