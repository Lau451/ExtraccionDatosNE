# Reglas — Pricing

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`) y sus tests (`tests/pricing/test_service.py`) en esta sesión.

### RN-PRICING-001 — El costo especial gana al costo estándar solo si es estrictamente menor

- **Descripción**: `resolver_costo` busca un precio especial puntual (por
  `item_proceso_id`) y, si no hay, uno general (por `producto_id` +
  `drogueria_id`); en paralelo busca el costo estándar vigente. El especial se usa
  como costo del ítem únicamente si existe y (no hay estándar, o el especial es
  menor que el estándar). Si el especial existe pero es igual o mayor al estándar,
  gana el estándar.
- **Condición**: `costo_especial is not None and (costo_estandar is None or
  costo_especial < costo_estandar)`.
- **Resultado**: `(costo_especial, "precio_especial", especial["id"],
  especial["mantenimiento_hasta"])` si gana el especial; `(costo_estandar,
  "costo_estandar", None, None)` si gana el estándar (o no hay especial); `(None,
  None, None, None)` si no hay ninguno de los dos.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:30-50`.
- **Observaciones**: [IMPLEMENTADO]. La búsqueda del especial puntual ordena por
  `precio_unitario` ascendente y toma la primera fila cuyo rango
  `cantidad_minima`/`cantidad_maxima` contiene la cantidad del ítem
  (`_primero_en_rango`, `repository.py:9-18`) — si hay varios precios especiales
  vigentes en rango, gana el más barato, no el más reciente ni el de mayor
  prioridad explícita. Verificada en
  `tests/pricing/test_service.py:58-116`
  (`test_precio_especial_gana_al_costo_estandar`, especial=60 < estándar=100 → gana
  el especial) y en `tests/pricing/test_service.py:9-55`
  (`test_generar_presupuesto_sin_mercado_usa_margen_objetivo`, sin especial → gana
  el estándar, `origen_costo == "costo_estandar"`).

### RN-PRICING-002 — El piso de margen es el costo incrementado en el margen mínimo de la regla

- **Descripción**: dado un costo resuelto y una regla de pricing aplicable, el piso
  es el costo multiplicado por `(1 + margen_minimo_pct/100)`, redondeado a 2
  decimales.
- **Condición**: cualquier llamada a `calcular_precio` con costo y regla no nulos.
- **Resultado**: `piso = _q(costo * (1 + margen_minimo_pct / 100))`, con `_q`
  redondeo `ROUND_HALF_UP` a 2 decimales.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:56-57`, `_q` en
  `service.py:22-23`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/pricing/test_service.py:167` (piso=100\*1.20=120, comentario explícito en
  el test) y `:224` (mismo piso, otro escenario).

### RN-PRICING-003 — Entre precio de mercado con descuento y piso de margen, gana el mayor; el piso nunca se perfora

- **Descripción**: si hay una muestra de mercado vigente (`v_precio_mercado_producto`
  dentro de la ventana de meses de la regla), se calcula una `referencia` como la
  mediana de mercado con el descuento de la regla aplicado. Si `referencia >= piso`,
  gana el mercado (`metodo_precio = "mercado"`); si no, gana el piso
  (`metodo_precio = "piso_margen"`) — el precio final nunca queda por debajo del
  margen mínimo configurado.
- **Condición**: `mediana is not None` (hay muestra de mercado en la ventana).
- **Resultado**: `referencia = _q(mediana * (1 - descuento_pct / 100))`; `precio,
  metodo = (referencia, "mercado") if referencia >= piso else (piso,
  "piso_margen")`. `descuento_pct` es `regla["descuento_vs_mercado_pct"]` o `0` si es
  `NULL`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:59-81`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en dos tests simétricos:
  `tests/pricing/test_service.py:119-173`
  (`test_mercado_gana_al_piso`, piso=120, mediana=200 sin descuento → referencia=200
  ≥ piso → gana mercado, precio final 200.00) y
  `tests/pricing/test_service.py:176-230`
  (`test_piso_gana_al_mercado`, piso=120, mediana=50 sin descuento → referencia=50 <
  piso → gana el piso, precio final 120.00). Ambos tests siembran el precio de
  mercado indirectamente vía `comparativas` + `ofertas_items` con
  `adjudicacion_estimada=True`, y confían en que `v_precio_mercado_producto` (vista,
  sin definición SQL en este repositorio) refleje esa oferta como mediana.

### RN-PRICING-004 — Una regla de pricing aplica por alcance opcional (droguería obligatoria, cliente/clase/categoría opcionales) y gana la de mayor prioridad

- **Descripción**: `buscar_regla_aplicable` filtra por `drogueria_id` y `activa=True`
  de forma obligatoria; para `cliente_id`, `clase_proceso` y `categoria_id`, una
  regla matchea si el campo de la regla es `NULL` (alcance general, aplica a
  cualquier valor) **o** coincide exactamente con el valor recibido (alcance
  específico). De las reglas que matchean los 3 alcances, gana la de mayor
  `prioridad`.
- **Condición**: cualquier llamada a `calcular_item` con `producto_id` resuelto.
- **Resultado**: `SELECT * FROM reglas_pricing WHERE drogueria_id=? AND activa=True
  AND (cliente_id IS NULL OR cliente_id=?) AND (clase_proceso IS NULL OR
  clase_proceso=?) AND (categoria_id IS NULL OR categoria_id=?) ORDER BY prioridad
  DESC LIMIT 1`, construido vía `_alcance_or` + `.or_()` encadenado tres veces
  (`repository.py:73-93`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/repository.py:67-93`.
- **Observaciones**: [IMPLEMENTADO]. `categoria_id` se resuelve desde
  `producto["categoria_id"]` (`service.py:127`) — si el producto no existe (caso
  extremo, dado que `producto_id` viene de un `items_proceso` con `producto_id NOT
  NULL`), se pasa `None`. `cliente_id` viene del `procesos_comerciales.cliente_id`
  del proceso completo, no del ítem. Verificada indirectamente en todos los tests de
  `generar_presupuesto` (la regla sembrada en `seed_regla_pricing`,
  `tests/pricing/conftest.py:34-46`, tiene los 3 campos de alcance en `NULL` por
  omisión — no hay un test dedicado a la resolución de alcance específico por
  cliente/clase/categoría en `tests/pricing/test_service.py`). Ver
  [`pendientes.md`](./pendientes.md) P1 para el riesgo de construcción del filtro
  (`_alcance_or`).

### RN-PRICING-005 — El stock disponible se verifica y se registra solo si el proceso es una cotización

- **Descripción**: `stock_verificado` y `stock_al_generar` solo se calculan cuando
  `clase_proceso == "cotizacion"`; para licitaciones quedan en `False`/`None`.
- **Condición**: `clase_proceso == "cotizacion"` (dentro de `calcular_item`, solo si
  ya se resolvió un precio — no se llega a esta rama si `resultado_precio is
  None`).
- **Resultado**: `stock_verificado = True`, `stock_al_generar = libre` (stock libre
  del producto en ese momento, no reservado ni comprometido por esta llamada — solo
  lectura). Para licitaciones o para ítems `sin_precio`: `stock_verificado = False`,
  `stock_al_generar = None`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:158-162`; función
  `verificar_stock` en `service.py:101-103` (delega en `repo.buscar_stock_libre`,
  `repository.py:112-121`, solo lectura, sin compromiso).
- **Observaciones**: [IMPLEMENTADO]. La verificación es informativa: no bloquea ni
  ajusta el precio ni la cantidad, solo deja constancia de cuánto stock libre había
  al momento de generar el presupuesto. El compromiso real de stock ocurre después,
  en `presupuestos.presentar_presupuesto` (`presupuestos/service.py:195-219`), y
  solo también para `clase == "cotizacion"` — mismo criterio replicado en el otro
  módulo. Verificada en
  `tests/pricing/test_service.py:9-55`
  (`test_generar_presupuesto_sin_mercado_usa_margen_objetivo`: proceso
  `"cotizacion"` con stock no sembrado explícitamente → `stock_verificado is True`,
  `stock_al_generar == Decimal("0")`). No se encontró en
  `tests/pricing/test_service.py` un test que siembre un proceso `"licitacion"`
  para confirmar `stock_verificado is False` en ese caso — cobertura no verificada
  para esa rama.

### RN-PRICING-006 — Sin precio de mercado en ventana, el precio cae al margen objetivo de la regla; si tampoco hay margen objetivo, el ítem queda sin precio

- **Descripción**: si `v_precio_mercado_producto` no devuelve fila para el producto
  dentro de la ventana de meses de la regla, `calcular_precio` calcula el precio
  como `costo * (1 + margen_objetivo_pct/100)`, con `metodo_precio =
  "margen_objetivo"`. Si además `margen_objetivo_pct` es `NULL` en la regla,
  `calcular_precio` devuelve `None` — el ítem cae a `metodo_precio = "sin_precio"`
  en `calcular_item` aun teniendo costo y regla resueltos.
- **Condición**: `mediana is None` (sin RN-PRICING-006) y, dentro de esa rama,
  `margen_objetivo_pct is None` (para el caso extremo de `sin_precio` con regla
  presente).
- **Resultado**: `precio = _q(costo * (1 + margen_objetivo_pct / 100))`,
  `metodo_precio = "margen_objetivo"` — o `None` completo si `margen_objetivo_pct`
  es `NULL`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:83-98`.
- **Observaciones**: [IMPLEMENTADO]. Verificada para el caso principal en
  `tests/pricing/test_service.py:9-55`
  (`test_generar_presupuesto_sin_mercado_usa_margen_objetivo`, costo=100,
  margen_objetivo=30 → precio=130.00). El caso extremo de `margen_objetivo_pct
  IS NULL` (regla con margen mínimo pero sin margen objetivo, y sin mercado) no
  tiene un test dedicado en `tests/pricing/test_service.py` — comportamiento
  verificado solo por lectura de código (`service.py:83-85`).

### RN-PRICING-007 — Un ítem del proceso sin `producto_id` resuelto queda completamente fuera del presupuesto

- **Descripción**: `buscar_items_con_producto` filtra `items_proceso` por
  `producto_id NOT NULL` — un ítem sin producto identificado (por ejemplo, aún no
  resuelto por el módulo de matching) no genera ninguna fila en
  `presupuesto_items`, ni suma a `cantidad_items` ni a `items_sin_precio`. No es lo
  mismo que un ítem `sin_precio` (que sí tiene `producto_id` pero no pudo calcular
  un precio): ese caso sí genera fila y sí cuenta.
- **Condición**: `item["producto_id"] IS NULL`.
- **Resultado**: la fila de `items_proceso` no aparece en el resultado de
  `buscar_items_con_producto` y por lo tanto nunca llega a `calcular_item`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/pricing/repository.py:158-166`
  (`.not_.is_("producto_id", None)`, línea 163).
- **Observaciones**: [IMPLEMENTADO] el filtro. No se encontró en
  `tests/pricing/test_service.py` un test que siembre un `items_proceso` sin
  `producto_id` para confirmar el efecto exacto sobre `cantidad_items` — inferido
  directamente del código. Ver [`pendientes.md`](./pendientes.md) para el riesgo
  funcional de que un presupuesto "completo" no refleje ítems aún no matcheados.

### RN-PRICING-008 — Regenerar un presupuesto abierto reemplaza sus ítems por completo, sin conservar ajustes manuales previos

- **Descripción**: si ya existe un presupuesto en estado `"generado"` o
  `"en_revision"` para el proceso comercial, `generar_presupuesto` borra **todas**
  las filas de `presupuesto_items` de ese presupuesto y las vuelve a insertar desde
  cero con el resultado del nuevo cálculo — sin distinguir ítems que hayan sido
  editados manualmente por `presupuestos.ajustar_item` de ítems nunca tocados.
- **Condición**: `existente is not None` (`buscar_presupuesto_abierto` encontró un
  presupuesto en estado `"generado"` o `"en_revision"` para el mismo
  `proceso_comercial_id`).
- **Resultado**: `DELETE FROM presupuesto_items WHERE presupuesto_id=?` seguido de
  un `INSERT` masivo con las filas recién calculadas (`service.py:275`,
  `:307-308`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/pricing/service.py:251-282`,
  `:306-308`.
- **Observaciones**: [IMPLEMENTADO]. Verificada en
  `tests/pricing/test_service.py:297-367`
  (`test_regenerar_presupuesto_no_deja_items_huerfanos`), que confirma que no
  quedan filas huérfanas y que el presupuesto y su `id` se reutilizan — pero ese
  test no cubre el escenario de un ítem previamente ajustado a mano vía
  `presupuestos.ajustar_item`, que es donde se pierde el ajuste. Ver
  [`arquitectura.md`](./arquitectura.md) y [`pendientes.md`](./pendientes.md) P1
  para el detalle de este riesgo.

### RN-PRICING-009 — El margen resultante se calcula sobre el costo usado, no sobre el precio de mercado ni el piso por separado

- **Descripción**: una vez elegido el precio final (mercado, piso o margen
  objetivo), el margen resultante que se persiste es `(precio - costo) / costo *
  100`, redondeado a 2 decimales — un dato informativo derivado, no un insumo del
  cálculo de precio.
- **Condición**: cualquier ítem con `resultado_precio` no nulo.
- **Resultado**: `margen_resultante_pct = _q((precio - costo) / costo * 100)`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/pricing/service.py:156`.
- **Observaciones**: [IMPLEMENTADO]. Sin guarda contra `costo == 0` en este punto
  (división por cero) — a diferencia de `presupuestos.ajustar_item`
  (`presupuestos/service.py:153-157`), que sí chequea `costo_usado > 0` antes de
  dividir. En la práctica, `costo` en este punto ya pasó por `resolver_costo`, que
  solo devuelve valores leídos de `precios_proveedor.precio_unitario` o
  `costos_productos.costo_unitario` — no hay validación explícita en este módulo
  de que esas columnas no acepten `0`. Ver [`pendientes.md`](./pendientes.md) P3.
