# Decisiones de diseño — Pricing

Numeración D-PRICING-NNN, verificada contra el código en esta sesión.

### D-PRICING-001 — Cascada de prioridad: costo especial > costo estándar; precio de mercado > piso de margen > margen objetivo

- **Decisión**: el costo de un ítem se resuelve primero contra `precios_proveedor`
  (precio especial, puntual o general) y solo cae a `costos_productos` (costo
  estándar) si no hay especial o el especial no es más barato (RN-PRICING-001).
  Sobre ese costo, el precio de venta se resuelve primero contra el precio de
  mercado con descuento, con el piso de margen mínimo como cota inferior
  (RN-PRICING-003), y solo cae al margen objetivo fijo si no hay dato de mercado
  (RN-PRICING-006).
- **Motivo**: pendiente de definición funcional — no hay comentario en el código que
  explique por qué se prioriza el costo/precio más específico (especial, de
  mercado) sobre el más genérico (estándar, margen fijo). Inferido de la estructura
  de datos: `precios_proveedor` y `v_precio_mercado_producto` representan
  información más reciente/específica de la operación concreta que
  `costos_productos`/`reglas_pricing`, que son configuración general.
- **Ventajas**: permite que un precio negociado puntualmente con un proveedor
  (costo especial) o una referencia de mercado reciente (precio de mercado)
  primen sobre valores de catálogo generales, sin perder la protección del margen
  mínimo (el piso nunca se perfora, RN-PRICING-003).
- **Desventajas**: la cascada tiene 4 niveles de fallback (especial→estándar,
  mercado→piso→margen objetivo→sin_precio) sin ningún log ni campo que indique
  explícitamente "se usó el nivel N por ausencia del nivel N-1" más allá de lo que
  se puede inferir de `origen_costo` y `metodo_precio` — para depurar por qué un
  ítem quedó `sin_precio`, hay que revisar manualmente si faltó costo, regla, o
  ambos (`ResultadoPricingItem` no distingue las tres causas con un campo propio).

### D-PRICING-002 — El stock solo se verifica (no se compromete) al generar el presupuesto, y solo para cotizaciones

- **Decisión**: `calcular_item` lee el stock libre y lo persiste como dato
  informativo (`stock_al_generar`) únicamente cuando `clase_proceso ==
  "cotizacion"` (RN-PRICING-005); no llama a ningún mecanismo de compromiso de
  `core/stock.py`.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código de
  `pricing/` que lo explique. Inferido de la separación de responsabilidad con
  `presupuestos/`: el compromiso real ocurre recién en
  `presupuestos.presentar_presupuesto` (`presupuestos/service.py:195-219`), que usa
  el mismo criterio `clase == "cotizacion"` — comprometer stock antes de que el
  presupuesto esté aprobado y presentado reservaría inventario para presupuestos
  que podrían nunca avanzar (por ejemplo, si quedan en borrador o se rechazan antes
  de aprobarse), inmovilizando stock sin necesidad.
- **Ventajas**: separa "cuánto stock había disponible al cotizar" (foto informativa,
  sin efectos secundarios) de "reservar ese stock" (acción con efectos, más
  adelante en el ciclo de vida) — evita comprometer inventario prematuramente por
  la sola generación de un presupuesto que aún puede regenerarse varias veces.
- **Desventajas**: `stock_al_generar` puede quedar desactualizado apenas se genera:
  entre la generación del presupuesto y su presentación (cuando sí se compromete),
  otro proceso puede consumir ese mismo stock — el dato persistido no se
  revalida automáticamente en `presentar_presupuesto`, que hace su propio
  compromiso independiente (con optimistic locking en `core/stock.py`, pero sin
  relación directa con el valor que Pricing dejó guardado).
- **Por qué solo cotizaciones**: licitaciones (`clase_proceso == "licitacion"`) no
  verifican ni registran stock en este paso — motivo no documentado en el código;
  posible hipótesis (no confirmada) es que una licitación es una oferta a futuro sin
  compromiso de entrega inmediata, a diferencia de una cotización — pendiente de
  definición funcional.

### D-PRICING-003 — Regenerar un presupuesto abierto reemplaza sus ítems en vez de aplicar un diff

- **Decisión**: `generar_presupuesto`, al encontrar un presupuesto ya abierto para
  el proceso, borra todos sus `presupuesto_items` y los reinserta desde cero
  (RN-PRICING-008), en vez de comparar fila por fila y actualizar solo lo que
  cambió.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código.
  Es la implementación más simple de "recalcular todo" y evita tener que resolver
  qué hacer con ítems que ya no están en `items_proceso` (por ejemplo, si un ítem
  fue eliminado del proceso entre una generación y la siguiente) sin necesidad de
  lógica de reconciliación explícita.
- **Ventajas**: garantiza que `presupuesto_items` siempre refleja exactamente el
  estado actual de `items_proceso` más el cálculo vigente, sin filas huérfanas —
  confirmado por `tests/pricing/test_service.py:297-367`.
- **Desventajas**: es también la causa directa del hallazgo de solapamiento con
  `presupuestos/` (ver [`arquitectura.md`](./arquitectura.md)): cualquier ajuste
  manual hecho por `presupuestos.ajustar_item` sobre un ítem (precio fijado a mano,
  exclusión con motivo) se pierde en la próxima regeneración, porque el `DELETE` no
  distingue ítems tocados manualmente de ítems nunca editados. No hay ninguna
  guarda ni advertencia en el código para este caso.

### D-PRICING-004 — El único endpoint de lectura de precios especiales bypasea `service.py`

- **Decisión**: `GET /precios-especiales` (`router.py:43-48`) consulta la vista
  `v_precios_especiales_vigentes` directo con `user_client`, sin pasar por ninguna
  función de `pricing/service.py` ni `pricing/repository.py`.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código.
  Es el único endpoint del módulo (y uno de los pocos en todo `presupuestacion/`,
  fuera de los `GET` con RLS de [`../catalogo/`](../catalogo/)) que hace esto.
- **Ventajas**: menos código para un endpoint puramente de lectura sin lógica de
  negocio — la vista ya resuelve "vigentes" en SQL.
- **Desventajas**: rompe la consistencia del resto del módulo (y del patrón general
  del proyecto) de que las rutas HTTP delegan en `service.py`; si en el futuro esta
  consulta necesitara lógica adicional (filtros, paginación, transformación), habría
  que moverla a `service.py`/`repository.py` primero. Ver
  [`pendientes.md`](./pendientes.md) P3.
