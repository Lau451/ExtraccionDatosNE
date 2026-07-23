# Flujos — Core

Cuatro flujos principales en los que Core participa. Cada paso cita `archivo:línea`
verificado en esta sesión.

## Flujo A — Compromiso de stock al presentar un presupuesto

Disparado por `presentar_presupuesto` en `presupuestos/service.py` cuando el proceso
comercial asociado es de clase `"cotizacion"`.

1. Se valida que el presupuesto exista y esté en estado `"aprobado"`
   (`services/presupuestacion/presupuestos/service.py:183-187`).
2. Se filtran los ítems del presupuesto a los que corresponde comprometer stock: no
   excluidos, con `producto_id` y `cantidad_ofertada` definidos
   (`presupuestos/service.py:195-201`).
3. Por cada ítem filtrado, se llama a `stock.comprometer_stock_producto`
   (`presupuestos/service.py:206-211`), que:
   1. Lista las filas de `stock_productos` del producto/droguería
      (`services/presupuestacion/core/stock.py:137`, usando
      `listar_stock_por_producto`, `core/stock.py:13-23`).
   2. Ordena los depósitos por mayor cantidad libre primero (`core/stock.py:138-142`,
      RN-CORE-003).
   3. Por cada depósito, llama a `_comprometer_hasta` (`core/stock.py:150`), que relee
      la fila, calcula lo libre, hace el UPDATE condicional con optimistic locking, y
      reintenta hasta 5 veces con backoff si pierde la carrera (`core/stock.py:68-92`,
      RN-CORE-001, RN-CORE-002).
   4. Si `_comprometer_hasta` agota reintentos y levanta `ConflictError`, se revierte lo
      ya comprometido en esta llamada (`core/stock.py:154-160`, vía
      `liberar_o_reportar`) y se relanza la excepción.
   5. Si al recorrer todos los depósitos queda un remanente sin cubrir, se arma un
      `ConflictError`, se revierte todo lo comprometido en la llamada y se lanza
      (`core/stock.py:162-168`, RN-CORE-004).
4. Si `comprometer_stock_producto` falla para algún ítem, `presentar_presupuesto`
   también revierte los compromisos ya acumulados de ítems **anteriores** del mismo
   presupuesto (`presupuestos/service.py:213-219`, vía `stock.liberar_o_reportar`), y
   relanza la excepción original.
5. Si todos los ítems se comprometieron sin error, se actualiza el presupuesto a estado
   `"presentado"` (`presupuestos/service.py:222-226`) y se registra el cambio de estado
   con `registrar_cambio` (`presupuestos/service.py:227-238`).
6. Se actualiza también el proceso comercial asociado a `"presentado"`
   (`presupuestos/service.py:239-241`) y se registra ese cambio con otro
   `registrar_cambio` (`presupuestos/service.py:242-253`).

## Flujo B — Resolución de usuario desde un JWT

Disparado en cada request a un endpoint protegido de `presupuestacion/` que declara
`Depends(require_roles(...))` o `Depends(get_current_user)`.

1. FastAPI resuelve la dependencia `get_bearer_token`
   (`services/presupuestacion/core/database.py:10-16`): exige el header
   `Authorization: Bearer <token>`; si falta o el esquema no es `bearer`, levanta
   `AuthenticationError` (RN-CORE-010).
2. `get_current_claims` (`services/presupuestacion/core/auth.py:24-29`) toma ese token y
   llama a `verificar_token` de `services/shared/auth_jwt.py:22-36`, que resuelve el
   JWKS de Supabase (`auth_jwt.py:16-19`, cacheado) y decodifica el JWT con los
   algoritmos `ES256`/`HS256` y `audience="authenticated"` (`auth_jwt.py:31-32`).
3. Si `verificar_token` levanta `TokenInvalidoError` (firma inválida, vencido o
   malformado, `auth_jwt.py:34-36`), `get_current_claims` lo traduce a
   `AuthenticationError` (`core/auth.py:27-28`).
4. Si el token es válido, `get_current_claims` devuelve un `UserClaims(sub, exp)`
   (`core/auth.py:29`).
5. `get_current_user` (`core/auth.py:32-45`) recibe esos claims junto con un
   `user_client` (vía `get_user_client`, que aplica RLS con el mismo token,
   `core/database.py:25-29`), y consulta
   `SELECT id, drogueria_id, rol FROM usuarios WHERE id = claims.sub`
   (`core/auth.py:36-42`).
6. Si no hay fila, levanta `NotFoundError("No se encontró el perfil de usuario")`
   (`core/auth.py:43-44`, RN-CORE-013). Si la hay, devuelve un `UsuarioPerfil`
   (`core/auth.py:45`).
7. Si el endpoint usó `require_roles(*roles)`, su dependencia interna valida
   `usuario.rol in roles`; si no pertenece, levanta `ForbiddenError`
   (`core/auth.py:48-54`, RN-CORE-012).
8. Cualquier `DomainError` levantada en los pasos anteriores es capturada por los
   handlers registrados una sola vez en el arranque de la aplicación
   (`register_exception_handlers(app)`, `services/presupuestacion/main.py:32`, que
   invoca `services/presupuestacion/core/exceptions.py:40-46`) y convertida en una
   `JSONResponse` con el status HTTP correspondiente a `STATUS_MAP`
   (`core/exceptions.py:31-37`, RN-CORE-009).

## Flujo C — Registro y lectura de auditoría

Disparado cuando un `service.py` de negocio necesita dejar rastro de un cambio, y
consumido después por lectura vía el endpoint HTTP de `auditoria/`.

1. Un service (p. ej. `eventos/service.py:128` o `presupuestos/service.py:76`) llama a
   `registrar_cambios` (`services/presupuestacion/core/audit.py:65-90`) con un
   diccionario `{campo: (valor_anterior, valor_nuevo)}`.
2. Si no se pasó `batch_id`, se genera uno con `uuid.uuid4()` (`core/audit.py:76`,
   RN-CORE-018).
3. Por cada campo del diccionario, se llama a `registrar_cambio`
   (`core/audit.py:78-89`), que:
   1. Resuelve la columna FK a partir de la entidad, vía `_COLUMNA_FK_POR_ENTIDAD`
      (`core/audit.py:53`, RN-CORE-020).
   2. Clasifica `tipo_cambio` como `"estado"` o `"campo"` según el nombre del campo
      (`core/audit.py:55`, RN-CORE-017).
   3. Serializa `valor_anterior`/`valor_nuevo` con `_a_texto` (`core/audit.py:21-28`,
      `:57-58`, RN-CORE-019).
   4. Inserta la fila en `historial_cambios` (`core/audit.py:62`).
4. Para eventos de ciclo de vida (creación, eliminación, restauración) se usa en cambio
   `registrar_evento_ciclo_vida` (`core/audit.py:93-114`), que inserta una única fila
   sin `campo` ni valores anterior/nuevo (`core/audit.py:105-113`).
5. La lectura ocurre vía `GET /historial/{entidad}/{entidad_id}`
   (`services/presupuestacion/auditoria/router.py:13-19`), protegido por
   `require_roles(*_ROLES_LECTURA)` (`auditoria/router.py:17`, RN-CORE-021) y resuelto
   con `get_user_client` (RLS, `auditoria/router.py:18`).
6. El endpoint filtra por la columna FK usando el mapeo **duplicado** de
   `auditoria/models.py:8-14` (independiente del de `core/audit.py:12-18` — ver
   `pendientes.md` P2(1); ambos mapeos coinciden hoy pero no hay ninguna garantía
   estructural de que sigan coincidiendo si uno se edita sin el otro).

## Flujo D — Entrega de orden de compra y ajuste de stock

Disparado por `crear_entrega` en `compras/service.py` al confirmar la recepción física
de mercadería de una orden de compra (OC).

1. Se valida que la OC exista y esté en un estado apto para recibir entregas
   (`services/presupuestacion/compras/service.py:218-225`).
2. Se valida que cada ítem de la entrega pertenezca a la OC
   (`compras/service.py:227-234`).
3. Se calcula el estado de la entrega y se inserta la fila de `entrega` y sus
   `entrega_items` (`compras/service.py:236-267`).
4. Por cada ítem de la entrega que tiene `producto_id` (los que no lo tienen se
   saltean, `compras/service.py:270-272`), se llama a `stock.entregar_stock_producto`
   (`compras/service.py:273-279`), que:
   1. Calcula `cantidad_aceptada = cantidad_entregada - cantidad_rechazada`
      (`services/presupuestacion/core/stock.py:298`, RN-CORE-006).
   2. **Pasada 1** — libera `cantidad_comprometida` por el total entregado, recorriendo
      los depósitos ordenados por mayor comprometida primero
      (`core/stock.py:301-311`, RN-CORE-006, RN-CORE-007), usando `_liberar_hasta` con
      el mismo mecanismo de optimistic locking y reintentos (`core/stock.py:211-239`).
   3. **Pasada 2** — descuenta `cantidad_disponible` por lo aceptado, recorriendo los
      depósitos ordenados por mayor disponible primero (`core/stock.py:313-323`,
      RN-CORE-006, RN-CORE-007), usando `_descontar_disponible_hasta`
      (`core/stock.py:242-270`).
   4. Ninguna de las dos pasadas revierte nada si no alcanza a cubrir el monto — cada
      una topea en lo que haya disponible en ese momento (`core/stock.py:294-296`,
      RN-CORE-008).
5. `crear_entrega` no revierte el registro de entrega/items ya insertado si
   `entregar_stock_producto` agota reintentos y levanta `ConflictError`: el registro
   parcial queda como rastro para reconciliación manual
   (`compras/service.py:211-217`, docstring de `crear_entrega`).
6. Se recalcula el estado de la orden de compra a partir de las entregas acumuladas
   (`compras/service.py:281`).
