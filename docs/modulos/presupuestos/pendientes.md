# Pendientes — Auditoría técnica de Presupuestos

Clasificación P1 (riesgo funcional/de seguridad relevante) / P2 (deuda técnica
relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión.

## P1 — Riesgos funcionales y de seguridad

1. **La guarda de transición de este módulo no protege el `UPDATE` de
   `procesos_comerciales.estado` que el mismo módulo dispara.** [IMPLEMENTADO],
   ya reportado como P1 desde el otro lado en
   [`../procesos_comerciales/pendientes.md`](../procesos_comerciales/pendientes.md)
   P1(1), **confirmado como consistente** desde este lado en esta sesión:
   `presentar_presupuesto` (`service.py:180-255`) sí valida rigurosamente el
   estado del **presupuesto** (RN-PRESUPUESTOS-003, `service.py:186-187`) antes
   de comprometer stock y transicionar — pero el `UPDATE` subsiguiente sobre
   `procesos_comerciales.estado` (`service.py:239-241`, vía
   `repository.py:actualizar_proceso_comercial`, `:68-71`) no verifica en qué
   estado estaba el proceso comercial. Nada impide, hoy, presentar un
   presupuesto cuyo proceso comercial ya esté en un estado terminal
   (`adjudicado`, `perdido`, `cerrado`, `cancelado`,
   `procesos_comerciales/repository.py:_ESTADOS_TERMINALES`) o que ya haya
   sido presentado por otra vía. La inconsistencia no es que ambos módulos
   difieran en rigor por descuido — es que las guardas de `presupuestos/`
   fueron diseñadas exclusivamente para su propio campo (`presupuestos.estado`)
   y nunca se extendieron al campo ajeno que la misma función también
   escribe. Ver [`estados.md`](./estados.md) para la comparación completa.

2. **4 de los 7 estados declarados de `presupuestos.estado` nunca son
   producidos por ningún código del repositorio.** [IMPLEMENTADO], confirmado
   por grep exhaustivo de `"en_revision"`, `"adjudicado"`, `"rechazado"` y
   `"vencido"` sobre todo `services/presupuestacion/` en esta sesión (ver
   [`estados.md`](./estados.md) para el detalle completo por estado). En
   particular, `en_revision` es aceptado como estado aprobable
   (`_ESTADOS_APROBABLES`, `service.py:16`) y como estado "abierto" para
   regeneración (`pricing.buscar_presupuesto_abierto`,
   `pricing/repository.py:151`) — es decir, **hay código que depende de que
   este estado sea alcanzable** — pero ninguna función lo asigna jamás. Si
   `en_revision` es un estado que se espera setear manualmente (por ejemplo,
   desde Supabase Studio) o que un flujo futuro todavía no implementado debería
   producir, el código actual no lo documenta ni lo impide; si es vestigial,
   sigue activo en la guarda de aprobación y en el filtro de "abierto" de
   `pricing/` sin ningún efecto práctico observable hoy. "Motivo pendiente de
   definición funcional" en ambos casos — no se encontró ningún comentario que
   lo aclare.

3. **`ajustar_item` no tiene ninguna guarda sobre el estado del presupuesto
   padre.** [IMPLEMENTADO], confirmado por lectura completa de
   `service.py:131-177`: un ítem puede ajustarse (precio, cantidad, exclusión)
   en cualquier estado del presupuesto, incluyendo `"presentado"` — después de
   que ya se comprometió stock real y se le mostró el presupuesto al cliente.
   Un ajuste de `cantidad_ofertada` posterior a la presentación no vuelve a
   comprometer ni liberar stock (esa lógica solo corre dentro de
   `presentar_presupuesto`, una única vez), por lo que `cantidad_ofertada` en
   `presupuesto_items` y `cantidad_comprometida` en `stock_productos` pueden
   quedar desincronizadas sin que ningún mecanismo de este módulo lo detecte o
   lo corrija. No se encontró en `tests/presupuestos/test_service.py` un test
   que ejercite un ajuste sobre un presupuesto ya `"presentado"` — comportamiento
   verificado solo por lectura de código.

## P2 — Deuda técnica relevante

1. **`ajustar_item` no audita los campos que cambia en `presupuesto_items`.**
   [IMPLEMENTADO]. A diferencia de `aprobar_presupuesto` y
   `presentar_presupuesto`, que registran explícitamente el cambio de `estado`
   con `registrar_cambio` (`service.py:116-127`, `:227-253`), `ajustar_item`
   solo dispara auditoría de forma indirecta, a través de
   `_recalcular_totales_presupuesto`, y únicamente para los campos del
   **presupuesto** (`monto_total`, `items_sin_precio`) — nunca para los campos
   del propio ítem (`precio_unitario`, `cantidad_ofertada`, `excluido`,
   `motivo_exclusion`, `metodo_precio`, `precio_original_motor`). El mapeo
   `_COLUMNA_FK_POR_ENTIDAD` de `core/audit.py:12-18` ni siquiera tiene una
   entrada para `"presupuesto_item"` como entidad auditable separada — no
   sería trivial agregar esa auditoría sin extender primero `core/audit.py`.
   Consecuencia: `GET /historial/{entidad}/{id}` (documentado en
   [`../core/`](../core/)) puede mostrar que un presupuesto cambió de estado,
   pero no puede mostrar quién ajustó manualmente un precio ni cuándo, más allá
   de lo que ya expone `precio_ajustado_por` en la propia fila (sin historial
   de ajustes sucesivos, solo el último).

2. **Sin transacción explícita entre el compromiso de stock, el `UPDATE` de
   `presupuestos` y el `UPDATE` de `procesos_comerciales`.** [IMPLEMENTADO].
   `presentar_presupuesto` (`service.py:180-255`) hace, en secuencia, N
   llamadas a `stock.comprometer_stock_producto` (una por ítem), un `UPDATE`
   de `presupuestos`, un `INSERT` de auditoría, un `UPDATE` de
   `procesos_comerciales`, y un segundo `INSERT` de auditoría — todas
   llamadas HTTP separadas a PostgREST, sin ninguna envoltura transaccional a
   nivel de aplicación. Si el proceso falla entre el compromiso de stock
   exitoso y el `UPDATE` de `presupuestos` (por ejemplo, caída del servicio),
   el stock queda comprometido pero el presupuesto sigue en `"aprobado"` — un
   reintento posterior de `presentar_presupuesto` volvería a comprometer stock
   para los mismos ítems, duplicando el compromiso, porque no hay ninguna
   verificación de idempotencia. Mismo patrón de riesgo ya señalado para
   [`../pricing/pendientes.md`](../pricing/pendientes.md) P2(3) y
   [`../catalogo/decisiones.md`](../catalogo/decisiones.md) D-CATALOGO-002. No
   es un bug reproducido en esta sesión, es una hipótesis razonable a partir de
   la lectura del código.

3. **Regenerar un presupuesto abierto pierde `precio_original_motor`,
   `excluido` y `motivo_exclusion` de cualquier ajuste manual previo.**
   [IMPLEMENTADO], ya documentado en detalle desde el lado de Pricing
   (RN-PRICING-008, D-PRICING-003,
   [`../pricing/arquitectura.md`](../pricing/arquitectura.md) P1(3)),
   confirmado desde este lado: los 3 campos que este módulo escribe de forma
   exclusiva (`ajustar_item`, `service.py:146-164`) viven en la misma fila de
   `presupuesto_items` que `pricing.generar_presupuesto` borra por completo en
   cada regeneración (`DELETE ... WHERE presupuesto_id=?`, sin excepción para
   filas ajustadas manualmente). Este módulo no tiene ningún mecanismo (por
   ejemplo, un flag o un campo de solo-lectura para `pricing/`) que impida o
   señale esta pérdida — la responsabilidad de no regenerar un presupuesto con
   ajustes manuales pendientes recae enteramente en el usuario o en el
   frontend, sin ninguna barrera de backend.

## P3 — Menor

1. **`ResultadoPresupuestoItem` (`models.py:18-27`) está declarado pero no se
   usa en ningún punto del código.** [IMPLEMENTADO], confirmado por grep: la
   única aparición del nombre en todo `services/presupuestacion/` es su propia
   declaración. `ajustar_item` devuelve un `dict` crudo
   (`service.py:177`, `router.py:99-114`, sin `response_model`) en vez de
   construir este modelo — el tipo existe pero no cumple ninguna función hoy.

2. **`GET /presupuestos/{id}` y `PATCH /presupuesto-items/{id}` no tienen
   `response_model` explícito.** [IMPLEMENTADO]. A diferencia de los 2
   endpoints de transición de estado (`ResultadoPresupuesto`), estos dos
   devuelven `list[dict]`/`dict` sin tipar (`router.py:65`, `:105`) — sin
   validación de forma de salida por FastAPI/Pydantic ni documentación
   automática de esquema en OpenAPI para estas dos respuestas.

3. **Sin test de integración HTTP para ninguno de los 4 endpoints.**
   [IMPLEMENTADO] la ausencia. Los 17 tests de
   `tests/presupuestos/test_service.py` llaman directo a las funciones de
   `service.py`/`repository.py`, ejercitando la lógica de negocio con
   `service_client` — ninguno pasa por `router.py`, por lo que las 2 funciones
   de validación de pertenencia a la droguería
   (`_validar_presupuesto_de_la_drogueria`, `_validar_item_de_la_drogueria`,
   RN-PRESUPUESTOS-016) y el ruteo por rol de la matriz de visibilidad
   (RN-PRESUPUESTOS-013) están verificadas solo por lectura de código, no por
   test automatizado.

4. **`motivo_exclusion` se acepta como `None` sin validación al excluir un
   ítem.** [IMPLEMENTADO]. `ajustar_item` escribe `campos["motivo_exclusion"] =
   motivo_exclusion` (`service.py:164`) sin exigir que sea no vacío cuando
   `excluido=True` — un ítem puede quedar excluido sin ningún motivo registrado,
   pese a que la vista `v_presupuesto_revision` expone la columna para
   revisión (`rls_final.sql:480`). Pendiente de definición funcional si esto es
   intencional (exclusión rápida sin fricción) o un descuido de validación.

No se detectó código muerto más allá de `ResultadoPresupuestoItem` (P3.1): las
funciones de `repository.py` y `service.py` tienen al menos un call site dentro
del propio módulo o son ejercitadas directo por
`tests/presupuestos/test_service.py` (confirmado leyendo ambos archivos
completos en esta sesión).
