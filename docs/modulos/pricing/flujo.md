# Flujos — Pricing

Los 2 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en
esta sesión.

## Flujo 1 — Cálculo de precio de un ítem (`calcular_item`)

Invocado internamente por `generar_presupuesto` una vez por cada ítem del proceso;
no tiene endpoint propio.

1. `calcular_item` recibe el ítem, `drogueria_id`, `clase_proceso` y `cliente_id`
   del proceso comercial (`service.py:106-113`).
2. **Resolver costo** (`resolver_costo`, `service.py:117-119`):
   1. Busca precio especial puntual por `item_proceso_id` (`repo.buscar_precio_especial_puntual`, `repository.py:21-34`); si no hay, busca uno general por `producto_id`+`drogueria_id` (`repo.buscar_precio_especial_general`, `repository.py:37-52`).
   2. Busca el costo estándar vigente (`repo.buscar_costo_estandar_vigente`, `repository.py:55-64`).
   3. Compara ambos: gana el especial solo si existe y es menor al estándar (RN-PRICING-001, `service.py:46-49`); si no, gana el estándar; si no hay ninguno, `costo = None`.
3. **Resolver producto y regla** (`service.py:121-128`):
   1. `repo.buscar_producto` trae `categoria_id` del producto (`repository.py:124-132`).
   2. `repo.buscar_regla_aplicable` busca la regla de mayor prioridad cuyo alcance (cliente/clase/categoría) matchea, vía `_alcance_or` (RN-PRICING-004, `repository.py:73-93`).
4. **Rama sin precio** (`service.py:130-136`): si `costo is None` o `regla is None`, no se llama a `calcular_precio` — el ítem va directo a la rama de resultado `sin_precio` (paso 6).
5. **Calcular precio** (`calcular_precio`, `service.py:53-98`, solo si hay costo y regla):
   1. Calcula el piso: `costo * (1 + margen_minimo_pct/100)` (RN-PRICING-002, `service.py:57`).
   2. Busca precio de mercado en la ventana de la regla (`repo.buscar_precio_mercado`, `repository.py:96-109`).
   3. Si hay mediana de mercado: calcula `referencia = mediana * (1 - descuento_pct/100)`; gana `referencia` si `>= piso`, si no gana el piso (RN-PRICING-003, `service.py:67-81`).
   4. Si no hay mediana: usa el margen objetivo de la regla; si tampoco hay margen objetivo, devuelve `None` (RN-PRICING-006, `service.py:83-98`).
6. **Armar el resultado** (`service.py:136-180`):
   - Si `resultado_precio is None` (sin costo, sin regla, o `calcular_precio` devolvió `None`): `ResultadoPricingItem` con `metodo_precio="sin_precio"`, `precio_unitario=None`, `stock_verificado=False` (`service.py:137-153`).
   - Si hay precio: calcula `margen_resultante_pct` (RN-PRICING-009, `service.py:156`); si `clase_proceso == "cotizacion"`, verifica stock libre (RN-PRICING-005, `service.py:158-162`, sin comprometerlo); arma `ResultadoPricingItem` completo (`service.py:164-180`).

## Flujo 2 — Generación/regeneración de presupuesto (`POST /procesos/{id}/generar-presupuesto`)

1. El router exige `require_roles(*_ROLES_GENERAR_PRESUPUESTO)` — `("superadmin",
   "admin", "gerencia", "lider_comercial", "comercial")` (`router.py:12`, `:19`).
2. `generar_presupuesto_endpoint` lee el proceso comercial con `user_client` (con
   RLS) para validar existencia y pertenencia (`router.py:22-28`) — `NotFoundError`
   si no existe.
3. Si `usuario.rol != "superadmin"` y la `drogueria_id` del proceso no coincide con
   la del usuario, `ForbiddenError` (`router.py:33-34`) — única validación de
   tenant hecha en el router, antes de delegar al service.
4. Llama a `generar_presupuesto_para_endpoint(proceso_comercial_id, drogueria_id,
   disparado_por=usuario.id)` (`router.py:36-40`), que resuelve
   `get_service_client()` internamente y delega en `generar_presupuesto`
   (`service.py:319-328`) — comentario textual verificado: *"Único punto donde
   `pricing` usa service_role — el router nunca lo importa directamente"*
   (`service.py:322`).
5. `generar_presupuesto` (`service.py:219-316`):
   1. Busca el proceso comercial con el `service_client`; `NotFoundError` si no existe (`service.py:222-224`).
   2. Trae los ítems del proceso con `producto_id` resuelto (RN-PRICING-007, `service.py:226`).
   3. Ejecuta el Flujo 1 (`calcular_item`) para cada ítem, con `clase_proceso` y `cliente_id` del proceso (`service.py:227-236`).
   4. Calcula `monto_total` (suma de `precio_unitario * cantidad_ofertada` de los ítems con precio), `items_sin_precio` (cuenta de `metodo_precio == "sin_precio"`) y `cantidad_items` (total de resultados, incluidos los `sin_precio`) (`service.py:238-249`).
   5. Busca si ya existe un presupuesto abierto (`estado` `"generado"` o `"en_revision"`) para el proceso (`repo.buscar_presupuesto_abierto`, `repository.py:146-155`).
   6. **Si no existe** (`service.py:254-272`): inserta la fila de `presupuestos` con `estado="generado"` y registra el evento de ciclo de vida `"creacion"` en `historial_cambios` vía `registrar_evento_ciclo_vida`.
   7. **Si ya existe** (`service.py:273-304`, RN-PRICING-008): borra todos los `presupuesto_items` del presupuesto, actualiza `presupuestos` con los nuevos totales, y registra en `historial_cambios` solo los campos que **efectivamente cambiaron** de valor (comparación explícita contra el estado anterior, `service.py:284-304`) vía `registrar_cambios`.
   8. Inserta las filas nuevas de `presupuesto_items`, una por resultado, si hay al menos una (`service.py:306-308`).
   9. Devuelve `ResultadoGenerarPresupuesto` con `presupuesto_id`, `monto_total`, `cantidad_items`, `items_sin_precio` y `regenerado` (`service.py:310-316`).
6. El endpoint responde con `ResultadoGenerarPresupuesto` (`router.py:16`,
   `response_model=ResultadoGenerarPresupuesto`).

No hay una transacción explícita a nivel de aplicación que envuelva el `DELETE` de
`presupuesto_items` y el `INSERT` posterior (paso 5.7 y 5.8): si el proceso falla
entre ambos pasos, el presupuesto queda con `presupuesto_items` vacío pero con
`presupuestos.monto_total`/`cantidad_items`/`items_sin_precio` ya actualizados —
mismo patrón de riesgo ya señalado para el versionado de costo de
[`../catalogo/decisiones.md`](../catalogo/decisiones.md) D-CATALOGO-002. Ver
[`pendientes.md`](./pendientes.md).

## Flujo informativo — `GET /precios-especiales`

No pasa por `pricing/service.py` ni `pricing/repository.py`: el router lee la vista
`v_precios_especiales_vigentes` directo con `user_client` (con RLS) dentro de
`precios_especiales_endpoint` (`router.py:43-48`) — el único endpoint de todo el
módulo que no delega en una función de `service.py`. Ver
[`casos_de_uso.md`](./casos_de_uso.md) y [`pendientes.md`](./pendientes.md) P3.
