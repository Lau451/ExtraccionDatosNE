# Reglas — Presupuestos

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`, `router.py`) y sus tests (`tests/presupuestos/test_service.py`,
17 casos) en esta sesión.

### RN-PRESUPUESTOS-001 — Solo se puede aprobar un presupuesto en estado `generado` o `en_revision`

- **Descripción**: `aprobar_presupuesto` rechaza la operación si el estado actual
  del presupuesto no está en `_ESTADOS_APROBABLES`.
- **Condición**: `presupuesto["estado"] not in ("generado", "en_revision")`.
- **Resultado**: `ConflictError("Solo se puede aprobar un presupuesto en estado
  'generado' o 'en_revision'")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:16` (constante
  `_ESTADOS_APROBABLES`), `:97-100` (guarda).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:93-111`
  (`test_aprobar_falla_si_el_estado_no_es_aprobable`, presupuesto sembrado en
  `"presentado"` → `ConflictError`). Ninguna función de este módulo ni de otro
  módulo leído en esta sesión escribe jamás `estado="en_revision"` sobre un
  presupuesto (confirmado por grep exhaustivo de `en_revision` en
  `services/presupuestacion/` — el único otro punto que lo menciona es el filtro
  de lectura `buscar_presupuesto_abierto` de `pricing/repository.py:151`). Es
  decir, en la práctica solo el camino `generado → aprobado` es alcanzable hoy.
  Ver [`estados.md`](./estados.md).

### RN-PRESUPUESTOS-002 — No se puede aprobar si quedan ítems `sin_precio` sin resolver

- **Descripción**: `aprobar_presupuesto` releé todos los ítems del presupuesto y
  bloquea la aprobación si alguno tiene `metodo_precio == "sin_precio"` y no está
  excluido.
- **Condición**: `_es_item_no_resuelto(item)` para al menos un ítem:
  `item["metodo_precio"] == "sin_precio" and not item["excluido"]`.
- **Resultado**: `ValidationError(f"Hay {len(no_resueltos)} ítem(s) sin precio
  sin resolver (excluir el renglón o fijar un precio manual)")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:27-28`
  (`_es_item_no_resuelto`), `:102-108` (guarda).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:18-36`
  (`test_aprobar_bloquea_si_hay_items_sin_precio_no_resueltos`) y en
  `tests/presupuestos/test_service.py:39-59`
  (`test_aprobar_permite_si_el_sin_precio_esta_excluido`, el mismo ítem
  `sin_precio` con `excluido=True` sí permite aprobar). La guarda relee
  `presupuesto_items` completo en cada llamada (`repo.listar_items_presupuesto`,
  `service.py:102`) en vez de confiar en el contador cacheado
  `presupuestos.items_sin_precio` — evita una condición de carrera contra un
  contador desactualizado, a costa de una consulta adicional en cada intento de
  aprobación.

### RN-PRESUPUESTOS-003 — Solo se puede presentar un presupuesto en estado `aprobado`

- **Descripción**: `presentar_presupuesto` rechaza la operación si el
  presupuesto no está exactamente en `"aprobado"`.
- **Condición**: `presupuesto["estado"] != "aprobado"`.
- **Resultado**: `ConflictError("Solo se puede presentar un presupuesto en
  estado 'aprobado'")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:186-187`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:296-309`
  (`test_presentar_bloquea_si_no_esta_aprobado`, presupuesto en `"generado"` →
  `ConflictError`). Esta es la misma guarda que
  [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md)
  cita textualmente para distinguirla de la ausencia de guarda sobre
  `procesos_comerciales.estado` — confirmado acá con la misma cita exacta
  (`service.py:186-187`): la condición es sobre el **estado del presupuesto**,
  no sobre el proceso comercial.

### RN-PRESUPUESTOS-004 — El compromiso de stock al presentar solo aplica si el proceso es una cotización

- **Descripción**: `presentar_presupuesto` solo entra a la rama de compromiso de
  stock si el proceso comercial asociado tiene `clase == "cotizacion"`; para
  licitaciones, la transición a `"presentado"` ocurre sin tocar
  `stock_productos`.
- **Condición**: `proceso["clase"] == "cotizacion"`.
- **Resultado**: rama de compromiso de stock (`service.py:196-219`) ejecutada o
  saltada por completo.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:195`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:312-362`
  (`test_presentar_cotizacion_compromete_stock`, `cantidad_comprometida` pasa a
  `8`) y en `tests/presupuestos/test_service.py:365-405`
  (`test_presentar_licitacion_no_toca_stock`, mismo escenario de datos, proceso
  `"licitacion"` → `cantidad_comprometida` queda en `0`). Mismo criterio
  `clase == "cotizacion"` que usa `pricing.verificar_stock` para decidir si
  informa `stock_al_generar` (RN-PRICING-005,
  [`../pricing/reglas.md`](../pricing/reglas.md)) — coherente entre ambos
  módulos, sin código compartido.

### RN-PRESUPUESTOS-005 — Solo se comprometen ítems no excluidos con producto y cantidad definidos

- **Descripción**: de los ítems del presupuesto, solo entran al compromiso de
  stock los que no están excluidos, tienen `producto_id` no nulo y
  `cantidad_ofertada` no nula.
- **Condición**: `not i["excluido"] and i["producto_id"] is not None and
  i["cantidad_ofertada"] is not None`.
- **Resultado**: lista `items_a_comprometer` filtrada antes de iterar.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:197-201`.
- **Observaciones**: [IMPLEMENTADO]. No se encontró en
  `tests/presupuestos/test_service.py` un test dedicado a un ítem excluido o sin
  `producto_id`/`cantidad_ofertada` dentro de un presupuesto que se presenta —
  cobertura no verificada para esa combinación específica, aunque el filtro en
  sí es una línea directa sin ambigüedad de lectura.

### RN-PRESUPUESTOS-006 — Ante un fallo de stock en cualquier ítem, se revierten todos los compromisos ya hechos en esa llamada

- **Descripción**: si `stock.comprometer_stock_producto` levanta `ConflictError`
  para cualquier ítem de la iteración, `presentar_presupuesto` revierte los
  compromisos ya acumulados de los ítems **anteriores** de esta misma llamada
  (`stock.liberar_o_reportar`) antes de relanzar la excepción original. El
  presupuesto no queda `"presentado"` y ningún compromiso parcial sobrevive.
- **Condición**: `ConflictError` levantado por `stock.comprometer_stock_producto`
  para cualquier ítem, en cualquier posición de la iteración.
- **Resultado**: `stock.liberar_o_reportar(client, compromisos_totales,
  motivo_original)` seguido de `raise` (relanza la excepción original, salvo que
  la propia reversión falle — ver Observaciones).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:203-219`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:408-467`
  (`test_presentar_con_stock_insuficiente_no_presenta_y_no_deja_compromisos_parciales`):
  dos ítems, el primero con stock suficiente (comprometido con éxito) y el
  segundo con stock insuficiente (`ConflictError`) → el test confirma que el
  compromiso del **primer** ítem también se revierte (`cantidad_comprometida ==
  0`) y que el presupuesto queda en `"aprobado"`, no `"presentado"`. El
  comentario del código (`service.py:214-218`) aclara que si la propia
  reversión (`liberar_o_reportar`) también falla, no se pierde el motivo
  original: se encadena (`raise ... from`) con el error de limpieza — mecanismo
  documentado en detalle en [`../core/stock.py`](../core/stock.py) y
  [`../core/flujo.md`](../core/flujo.md) Flujo A, no repetido acá.

### RN-PRESUPUESTOS-007 — Presentar un presupuesto también fuerza `procesos_comerciales.estado` a `"presentado"`, sin guarda sobre el estado anterior

- **Descripción**: como último paso de `presentar_presupuesto`, se actualiza el
  proceso comercial asociado a `estado="presentado"`, sin verificar en qué
  estado estaba antes.
- **Condición**: siempre que `presentar_presupuesto` complete sin excepción
  (después de comprometer stock si corresponde).
- **Resultado**: `repo.actualizar_proceso_comercial(client,
  proceso_comercial_id=proceso["id"], campos={"estado": "presentado"})`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:239-241`.
- **Observaciones**: [IMPLEMENTADO]. Ya documentado con la misma cita exacta
  desde el otro lado en
  [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md)
  ("Ausencia confirmada de guardas de transición") y
  [`../procesos_comerciales/pendientes.md`](../procesos_comerciales/pendientes.md)
  P1(1)/P2(1) — confirmado acá: no hay `SELECT` previo del `estado` del proceso
  comercial más allá del que ya se trajo al inicio de la función
  (`buscar_proceso_comercial`, `service.py:189-191`, que solo se usa como
  `valor_anterior` de auditoría, `service.py:248`), y ninguna condición
  `WHERE estado=...` en el `UPDATE` (`repository.py:68-71`). Verificada en
  `tests/presupuestos/test_service.py:312-362` (el proceso pasa a
  `"presentado"`) y `tests/presupuestos/test_service.py:470-511`
  (`test_presentar_registra_historial_del_proceso_comercial`, confirma el
  registro de auditoría del cambio). Nada impide, hoy, presentar un presupuesto
  cuyo proceso comercial ya esté en un estado terminal
  (`adjudicado`/`perdido`/`cerrado`/`cancelado`, ver
  [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md)).

### RN-PRESUPUESTOS-008 — `precio_original_motor` se guarda solo la primera vez que se ajusta el precio a mano

- **Descripción**: al ajustar `precio_unitario` manualmente, si
  `precio_original_motor` todavía es `NULL`, se copia ahí el valor de
  `precio_unitario` **antes** de sobrescribirlo. En ajustes posteriores, no se
  vuelve a tocar.
- **Condición**: `precio_unitario is not None` (se está ajustando el precio) y
  `item["precio_original_motor"] is None` (primer ajuste).
- **Resultado**: `campos["precio_original_motor"] = item["precio_unitario"]`
  (valor previo a este ajuste) antes de `campos["precio_unitario"] =
  str(precio_unitario)` (valor nuevo).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:146-149`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:114-149`
  (`test_ajustar_item_guarda_precio_original_y_recalcula_margen`, precio motor
  `130.00` → ajuste a `150.00`, `precio_original_motor == 130.00`) y, de forma
  más directa, en `tests/presupuestos/test_service.py:152-193`
  (`test_ajustar_item_no_pisa_precio_original_motor_en_segundo_ajuste`: dos
  ajustes sucesivos, `150.00` y luego `160.00` — `precio_original_motor` se
  mantiene en `130.00` después de ambos, confirmando que solo el primer ajuste
  lo setea).

### RN-PRESUPUESTOS-009 — El margen resultante se recalcula contra `costo_usado`, con guarda de división por cero

- **Descripción**: cada vez que se ajusta `precio_unitario`, se recalcula
  `margen_resultante_pct` como `(precio_nuevo - costo_usado) / costo_usado *
  100`, redondeado a 2 decimales, siempre que `costo_usado` sea mayor a cero. Si
  no hay `costo_usado` o es `0`, el margen queda en `NULL`.
- **Condición**: `precio_unitario is not None` (dentro de la rama de ajuste de
  precio); `costo_usado is not None and costo_usado > 0`.
- **Resultado**: `margen_resultante_pct = _q((precio_unitario - costo_usado) /
  costo_usado * 100)`, o `None` si la condición de guarda no se cumple.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:153-157`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:114-149` (costo=100.00, precio
  ajustado=150.00 → margen=50.00%). A diferencia de
  `pricing.service.py:156` (RN-PRICING-009,
  [`../pricing/reglas.md`](../pricing/reglas.md)), que no chequea
  `costo > 0` antes de dividir, esta función sí lo hace — inconsistencia entre
  ambos módulos para el mismo tipo de cálculo, ya señalada desde el lado de
  Pricing. No se encontró en `tests/presupuestos/test_service.py` un test
  dedicado al caso `costo_usado IS NULL` o `costo_usado == 0` — comportamiento
  verificado solo por lectura de código.

### RN-PRESUPUESTOS-010 — Ajustar un ítem exige especificar al menos un campo

- **Descripción**: si `ajustar_item` recibe `precio_unitario`,
  `cantidad_ofertada` y `excluido` todos en `None`, no hay nada que escribir y
  la operación se rechaza.
- **Condición**: el diccionario `campos` queda vacío tras evaluar las tres
  ramas condicionales.
- **Resultado**: `ValidationError("No se especificó ningún campo para
  ajustar")`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:166-167`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:270-293`
  (`test_ajustar_item_sin_campos_levanta_validation_error`).

### RN-PRESUPUESTOS-011 — El recálculo de totales excluye los ítems marcados como excluidos

- **Descripción**: `_recalcular_totales_presupuesto` recalcula `monto_total`
  (suma de `precio_unitario * cantidad_ofertada`) e `items_sin_precio` a partir
  únicamente de los ítems con `excluido == False` — un ítem excluido no aporta a
  ninguno de los dos totales, sin importar su precio o método.
- **Condición**: `not i["excluido"]` para cada ítem considerado.
- **Resultado**: `activos = [i for i in items if not i["excluido"]]`, base de
  ambos cálculos.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:41-57`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:196-231`
  (`test_ajustar_item_recalcula_monto_total_del_presupuesto`, un ajuste de
  precio recalcula `monto_total` de `1300.00` a `1500.00`) y en
  `tests/presupuestos/test_service.py:234-267`
  (`test_ajustar_item_excluir_lo_saca_del_monto_total`, excluir el único ítem
  del presupuesto deja `monto_total == 0.00`). Este es el mismo criterio que
  [`../pricing/arquitectura.md`](../pricing/arquitectura.md) ya documentó desde
  el otro lado como divergente del cálculo de `pricing/` (que no conoce el
  campo `excluido` porque solo `presupuestos/` lo escribe) — confirmado acá con
  la misma cita exacta (`service.py:45`, `activos = [i for i in items if not
  i["excluido"]]`).

### RN-PRESUPUESTOS-012 — El recálculo de totales solo escribe y audita si hubo un cambio real

- **Descripción**: `_recalcular_totales_presupuesto` compara el `monto_total` e
  `items_sin_precio` recién calculados contra los valores actuales del
  presupuesto; si ambos coinciden, no hace ningún `UPDATE` ni registro de
  auditoría — devuelve el presupuesto sin tocar.
- **Condición**: `monto_anterior == monto_total and presupuesto["items_sin_precio"]
  == items_sin_precio` (ambas comparaciones, no solo una).
- **Resultado**: si no hay `cambios`, `return presupuesto` (sin `UPDATE`); si
  hay al menos un cambio, `UPDATE` de ambos campos juntos y un
  `registrar_cambio` por cada campo que efectivamente cambió, agrupados en el
  mismo `batch_id`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:60-88`.
- **Observaciones**: [IMPLEMENTADO]. El `UPDATE` en sí siempre escribe ambos
  campos si hay algún cambio (`campos={"monto_total": ..., "items_sin_precio":
  ...}`, `service.py:71-73`) aunque solo uno de los dos haya variado — el
  ahorro de escritura es "todo o nada" (cero updates vs. un update de ambos),
  no un `UPDATE` parcial por campo. La auditoría sí es granular: solo se llama
  `registrar_cambio` por cada campo presente en el diccionario `cambios`
  (`service.py:75-87`). No se encontró un test dedicado a confirmar la ausencia
  de escritura cuando no hay cambio real (el escenario de ajustar
  `cantidad_ofertada` sin que cambie el precio ni la exclusión no está cubierto
  en `tests/presupuestos/test_service.py`) — comportamiento verificado por
  lectura de código.

### RN-PRESUPUESTOS-013 — La visibilidad de un presupuesto depende del rol: dos vistas SQL distintas, seleccionadas por el router

- **Descripción**: `GET /presupuestos/{id}` no arma una respuesta única — elige
  entre `v_presupuesto_comercial` (sin costo) y `v_presupuesto_revision` (con
  costo y `alerta_mantenimiento`) según si el rol del solicitante está en
  `_ROLES_VEN_COSTO`.
- **Condición**: `usuario.rol in ("superadmin", "admin", "gerencia")` → vista de
  revisión; cualquier otro rol autorizado a leer (`comercial`,
  `lider_comercial`) → vista comercial.
- **Resultado**: `repo.listar_presupuesto_revision(...)` o
  `repo.listar_presupuesto_comercial(...)`, ambas con `user_client` (RLS
  aplicado además de la selección de vista).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/router.py:21` (constante
  `_ROLES_VEN_COSTO`), `:66-73` (selección, con comentario textual explícito:
  *"comercial/lider_comercial ven v_presupuesto_comercial (sin costo_usado ni
  detalle_calculo); admin/gerencia/superadmin ven v_presupuesto_revision
  completa (incluye alerta_mantenimiento)"*).
- **Observaciones**: [IMPLEMENTADO]. Verificada indirectamente en
  `tests/presupuestos/test_service.py:514-540`
  (`test_v_presupuesto_comercial_no_expone_costo`, `"costo_usado" not in
  filas[0]`) y `tests/presupuestos/test_service.py:543-569`
  (`test_v_presupuesto_revision_expone_costo_y_alerta_mantenimiento`,
  `"alerta_mantenimiento" in filas[0]`) — ambos tests ejercitan las funciones de
  `repository.py` directo, no el endpoint HTTP completo con distintos roles; no
  se encontró en `tests/presupuestos/test_service.py` un test de integración
  HTTP que confirme el ruteo por rol del propio `router.py:66-73`. Ver
  [`arquitectura.md`](./arquitectura.md) para el detalle de columnas de cada
  vista y el motivo (RLS filtra filas, no columnas).

### RN-PRESUPUESTOS-014 — Aprobar y ajustar corren con `service_role` porque la RLS de `presupuestos`/`presupuesto_items` no incluye `superadmin` en `UPDATE`

- **Descripción**: `aprobar_presupuesto_para_endpoint` y
  `ajustar_item_para_endpoint` resuelven `get_service_client()` (sin RLS) en vez
  de recibir el `user_client` del solicitante, porque las políticas RLS de
  `UPDATE` sobre ambas tablas no incluyen el rol `superadmin`.
- **Condición**: siempre, para cualquier solicitante autorizado por
  `require_roles`, independientemente de su rol real.
- **Resultado**: la escritura de `aprobar_presupuesto`/`ajustar_item` corre sin
  RLS, con las validaciones de pertenencia a la droguería ya hechas por el
  router con `user_client` antes de delegar.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:258-261`
  (`aprobar_presupuesto_para_endpoint`, docstring: *"la RLS de presupuestos no
  incluye 'superadmin' en UPDATE — mismo criterio que pricing/matching, el
  router nunca importa el service client"*), `:264-281`
  (`ajustar_item_para_endpoint`).
- **Observaciones**: [IMPLEMENTADO]. Confirmado contra el schema real:
  `docs/schema/rls_final.sql:254` (`pre_upd`) y `:264` (`pi_upd`) —
  `(select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')`,
  sin `superadmin` en ninguna de las dos políticas de `UPDATE`. El
  `_validar_presupuesto_de_la_drogueria`/`_validar_item_de_la_drogueria` del
  router (`router.py:24-57`) sí usa `user_client`, por lo que la comprobación
  de tenant se hace con RLS antes de la escritura sin RLS.

### RN-PRESUPUESTOS-015 — Presentar corre con `service_role` porque comprometer stock requiere permisos que ningún rol comercial (ni `superadmin`) tiene por RLS

- **Descripción**: `presentar_presupuesto_para_endpoint` también resuelve
  `service_role`, con un motivo adicional al de RN-PRESUPUESTOS-014: comprometer
  stock escribe `stock_productos`, cuya RLS de `UPDATE` solo permite
  `admin`/`gerencia`/`compras` — ni `comercial`/`lider_comercial` (que sí pueden
  presentar) ni `superadmin` podrían hacerlo vía `user_client`.
- **Condición**: siempre, para cualquier solicitante autorizado por
  `_ROLES_PRESENTAR`.
- **Resultado**: `presentar_presupuesto` corre con `service_client`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:284-290`
  (docstring: *"comprometer stock escribe stock_productos, cuya RLS solo
  permite admin/gerencia/compras en UPDATE — ningún rol comercial (ni
  superadmin) podría comprometer stock vía user_client"*).
- **Observaciones**: [IMPLEMENTADO]. Confirmado contra el schema real:
  `docs/schema/rls_final.sql:190` (`stock_upd`) —
  `(select get_rol()) IN ('admin','gerencia','compras')`. El rol `comercial`
  (que sí está en `_ROLES_PRESENTAR`, `router.py:19`) no está en esa lista, ni
  tampoco `lider_comercial` ni `superadmin` — la cita del docstring es exacta.

### RN-PRESUPUESTOS-016 — El router valida pertenencia a la droguería antes de delegar en cualquier escritura

- **Descripción**: los 3 endpoints de escritura (`aprobar`, `presentar`,
  `PATCH` de ítem) resuelven primero, con `user_client` (RLS), si el
  presupuesto/ítem pertenece a la droguería del solicitante — antes de llamar a
  la función `_para_endpoint` correspondiente (que corre con `service_role`, sin
  RLS).
- **Condición**: `usuario.rol != "superadmin" and
  presupuesto_drogueria_id != usuario.drogueria_id` (o el equivalente para
  ítems).
- **Resultado**: `ForbiddenError("El presupuesto no pertenece a tu droguería")`
  / `ForbiddenError("El ítem no pertenece a tu droguería")`; `NotFoundError` si
  la fila no existe siquiera bajo RLS.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/presupuestos/router.py:24-39`
  (`_validar_presupuesto_de_la_drogueria`), `:42-57`
  (`_validar_item_de_la_drogueria`), invocadas en `:85`, `:95`, `:106`.
- **Observaciones**: [IMPLEMENTADO]. Este patrón es necesario precisamente
  porque las funciones de negocio corren con `service_role` sin RLS
  (RN-PRESUPUESTOS-014/015) — sin esta validación previa con `user_client`,
  cualquier solicitante autenticado con el rol correcto podría aprobar/ajustar/
  presentar un presupuesto de otra droguería. No se encontró en
  `tests/presupuestos/test_service.py` un test de integración HTTP que ejercite
  el router completo (los 17 tests llaman directo a las funciones de
  `service.py`) — cobertura de esta guarda no verificada por test, solo por
  lectura de código.

### RN-PRESUPUESTOS-017 — Todo cambio de estado y todo recálculo de totales queda auditado en `historial_cambios`

- **Descripción**: cada transición de estado (`aprobar`, `presentar`, y el
  cambio de `procesos_comerciales.estado` como efecto colateral) y cada campo
  que cambia en `_recalcular_totales_presupuesto` se registra con
  `core.audit.registrar_cambio`, agrupado por `batch_id`.
- **Condición**: cualquier ejecución exitosa de `aprobar_presupuesto`,
  `presentar_presupuesto`, o `ajustar_item` que dispare un cambio real de
  totales.
- **Resultado**: una fila en `historial_cambios` por campo cambiado, con
  `entidad="presupuesto"` o `entidad="proceso_comercial"` según corresponda.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/presupuestos/service.py:116-127`
  (aprobar), `:227-238` (presentar, presupuesto), `:242-253` (presentar,
  proceso comercial), `:74-87` (recálculo de totales).
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/presupuestos/test_service.py:62-90`
  (`test_aprobar_setea_estado_y_audita`) y
  `tests/presupuestos/test_service.py:470-511`
  (`test_presentar_registra_historial_del_proceso_comercial`). `ajustar_item`
  en sí **no** llama a `registrar_cambio` directamente para los campos del
  ítem (`precio_unitario`, `excluido`, etc.) — solo audita indirectamente los
  totales del presupuesto padre a través de `_recalcular_totales_presupuesto`
  si estos cambian; no queda ningún registro de auditoría específico de
  `presupuesto_items` en `historial_cambios` (`_COLUMNA_FK_POR_ENTIDAD` de
  `core/audit.py:12-18` ni siquiera tiene una entrada para `"presupuesto_item"`
  como entidad separada). Ver [`pendientes.md`](./pendientes.md).

### RN-PRESUPUESTOS-018 — La base de datos exige `aprobado_por`/`aprobado_at` para todo estado posterior a la aprobación

- **Descripción**: el `CHECK ck_pre_aprobado` de la tabla `presupuestos` obliga
  a que `aprobado_por` y `aprobado_at` estén seteados salvo en los estados
  `generado`, `en_revision` o `vencido`.
- **Condición**: `estado NOT IN ('generado', 'en_revision', 'vencido')`.
- **Resultado**: el `INSERT`/`UPDATE` falla en Postgres si `aprobado_at IS NULL
  OR aprobado_por IS NULL` para cualquier otro estado (`aprobado`,
  `presentado`, `adjudicado`, `rechazado`).
- **Prioridad**: Media.
- **Archivo**: `docs/schema/extractor_final.sql:511-514`.
- **Observaciones**: [IMPLEMENTADO], constraint de base de datos, no de
  aplicación — complementa (no reemplaza) la guarda de aplicación de
  `aprobar_presupuesto` (RN-PRESUPUESTOS-001): incluso si algún código futuro
  bypaseara la guarda de `service.py` y forzara `estado="presentado"`
  directamente contra la tabla, Postgres seguiría exigiendo `aprobado_por`/
  `aprobado_at`. No hay un `CHECK` equivalente para `presentado_por`/
  `presentado_at` (no se encontró en el schema leído en esta sesión) — un
  `estado="presentado"` sin `presentado_por` sería aceptado por la base de
  datos.
