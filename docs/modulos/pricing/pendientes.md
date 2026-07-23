# Pendientes — Auditoría técnica de Pricing

Clasificación P1 (riesgo funcional/de seguridad relevante) / P2 (deuda técnica
relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión.

## P1 — Riesgos funcionales y de seguridad

1. **`_alcance_or` construye un filtro PostgREST por interpolación directa de
   string, sin escapar el valor.** [IMPLEMENTADO], cita exacta verificada,
   `repository.py:67-70`:

   ```python
   def _alcance_or(columna: str, valor: str | None) -> str:
       if valor is None:
           return f"{columna}.is.null"
       return f"{columna}.is.null,{columna}.eq.{valor}"
   ```

   Este string se pasa directo a `.or_()` de `postgrest-py` (`repository.py:86-88`),
   que lo interpreta como una lista de condiciones separadas por coma. Si `valor`
   contuviera una coma o un punto, podría alterar la estructura del filtro
   (agregar una condición extra, o corromper el nombre de columna/operador de la
   condición existente) — un patrón de inyección de filtro conceptualmente análogo
   a una inyección SQL, aunque contenido dentro del lenguaje de query de PostgREST,
   no de SQL crudo.

   **Evaluación de explotabilidad real, hecha en esta sesión revisando los 3 call
   sites de `_alcance_or` en `buscar_regla_aplicable` (`repository.py:73-93`)**:

   - `clase_proceso` (`repository.py:87`): viene de `proceso["clase"]`
     (`service.py:232`), y `procesos_comerciales/models.py:7` lo tipa como `Clase =
     Literal["cotizacion", "licitacion"]` en los modelos `ProcesoComercialCreate`/
     `Update` — **no** contiene `,` ni `.`. Hoy no explotable por esta vía, siempre
     que la única forma de escribir `procesos_comerciales.clase` sea a través de
     ese módulo (no verificado exhaustivamente en esta sesión si algún import
     masivo escribe `clase` sin pasar por el modelo Pydantic).
   - `cliente_id` (`repository.py:86`): viene de `proceso["cliente_id"]`
     (`service.py:233`). **`procesos_comerciales/models.py:24,45` tipa este campo
     como `cliente_id: str | None`, sin ningún validador de formato UUID** — un
     `POST`/`PATCH` de proceso comercial con un `cliente_id` que contenga `,` o `.`
     pasaría la validación Pydantic sin error.
   - `categoria_id` (`repository.py:88`): viene de `producto["categoria_id"]`
     (`service.py:127`). **`catalogo/models.py:16,27,42` tipa este campo igual,
     `categoria_id: str | None`, sin validador de formato UUID** — mismo caso.

   La única barrera real contra estos dos últimos vectores es el tipo de columna en
   Postgres: si `procesos_comerciales.cliente_id` y `productos.categoria_id` son
   columnas `uuid` (no `text`), Postgres rechaza en el `INSERT`/`UPDATE` cualquier
   valor que no tenga formato UUID válido — que por definición no contiene `,` ni
   `.` como caracteres sueltos fuera de los guiones del formato. **No se pudo
   verificar el tipo de columna en esta sesión**: no hay migraciones SQL de
   `presupuestacion/` versionadas en este repositorio (el schema se administra
   directo en Supabase). Si esas columnas fueran `text`/`varchar` en vez de `uuid`,
   el vector sería explotable hoy vía cualquier endpoint de escritura de
   `procesos_comerciales` o `catalogo` que acepte esos campos.

   **Clasificación de severidad (criterio propio)**: **P1**, no P2, por tres
   motivos independientes del resultado de la verificación de schema pendiente:
   (a) el patrón de código en sí — interpolación sin escapar en un filtro de
   query — es un antipatrón de seguridad que debería corregirse
   independientemente de si hoy es explotable, porque un cambio futuro en
   cualquiera de los dos módulos que escriben estos campos (agregar un endpoint
   de import masivo, relajar el tipo de columna, etc.) lo activaría sin que nada
   en `pricing/` lo señale; (b) la exploitabilidad depende hoy de una propiedad de
   la base de datos que no está verificada ni documentada en el código de
   aplicación — no hay ningún comentario en `pricing/repository.py` que documente
   esta dependencia implícita de que las columnas sean `uuid`; (c) es la única
   función de todo el módulo que construye un filtro por f-string en vez de
   usar los métodos tipados de `postgrest-py` (`.eq()`, `.is_()`) como hace el
   resto de `repository.py` — una corrección directa (escapar `valor`, o
   reemplazar `.or_()` por dos/tres queries separadas y combinar en Python) es
   de bajo costo y elimina el riesgo sin depender de verificar el schema.

2. **Regenerar un presupuesto que ya avanzó de estado crea un presupuesto nuevo
   para el mismo proceso, en vez de rechazar la operación.** [IMPLEMENTADO].
   `buscar_presupuesto_abierto` (`repository.py:146-155`) solo considera "abierto"
   un presupuesto en `"generado"`/`"en_revision"`. Si ya está `"aprobado"`,
   `"presentado"`, `"adjudicado"`, `"rechazado"` o `"vencido"`, una nueva llamada a
   `POST /procesos/{id}/generar-presupuesto` inserta una fila **nueva** en
   `presupuestos` para el mismo `proceso_comercial_id` (`service.py:251-272`), sin
   ningún chequeo de que ya exista un presupuesto avanzado para ese proceso. No se
   pudo confirmar en esta sesión si hay una constraint de base de datos que lo
   impida (sin schema SQL local de `presupuestacion/`). Si no la hay, un proceso
   comercial podría terminar con múltiples filas de `presupuestos` sin relación
   entre sí — ninguna de las 5 tablas leídas o escritas por este módulo tiene, del
   lado del código Python, una validación explícita de "un proceso comercial tiene
   a lo sumo un presupuesto no descartado". Ver
   [`arquitectura.md`](./arquitectura.md).

3. **Regenerar un presupuesto abierto borra ajustes manuales previos de
   `presupuestos.ajustar_item` sin ninguna advertencia.** [IMPLEMENTADO]
   (RN-PRICING-008, D-PRICING-003). Si un usuario ajustó a mano el precio o excluyó
   un ítem vía `presupuestos.ajustar_item` (`presupuestos/service.py:131-177`) y
   luego alguien vuelve a llamar `POST /procesos/{id}/generar-presupuesto` mientras
   el presupuesto sigue en `"generado"`/`"en_revision"`, el `DELETE +
   INSERT` de `presupuesto_items` (`service.py:275`, `:307-308`) pisa ese ajuste
   sin dejar rastro de que existía uno — el nuevo cálculo no consulta
   `precio_original_motor`, `excluido` ni `motivo_exclusion` de la fila anterior
   antes de borrarla. `historial_cambios` sí queda con el evento de la
   regeneración (RN-PRICING-008), pero no con un registro específico de "se perdió
   un ajuste manual".

4. **Ninguna operación de escritura sobre `reglas_pricing` ni `precios_proveedor`
   existe en el backend.** [IMPLEMENTADO] la ausencia, confirmado por grep
   exhaustivo en esta sesión sobre todo `services/presupuestacion/`: las únicas
   referencias a ambas tablas fuera de `pricing/repository.py` (que solo hace
   `SELECT`) están en fixtures de test, que insertan directo con `service_client`
   (`tests/pricing/conftest.py:34-46`, `tests/pricing/test_service.py:71-85`). Esto
   significa que toda la cascada de cálculo de precio de este módulo depende de
   datos que, en producción, solo pueden mantenerse escribiendo directo en la base
   (Supabase Studio o equivalente) — sin ningún endpoint, validación de negocio ni
   registro de auditoría para altas/bajas/cambios de reglas de margen o precios
   especiales por proveedor. Cualquier error de carga (por ejemplo, una regla con
   `margen_minimo_pct` negativo, o dos reglas con la misma prioridad y alcance
   superpuesto) no tiene ninguna validación de aplicación que lo prevenga.

## P2 — Deuda técnica relevante

1. **Dos implementaciones independientes del mismo cálculo de totales de
   presupuesto, con criterios distintos.** [IMPLEMENTADO] (ver
   [`arquitectura.md`](./arquitectura.md) para el detalle completo). Pricing
   calcula `monto_total`/`items_sin_precio` sobre **todos** los ítems
   (`service.py:238-249`); `presupuestos._recalcular_totales_presupuesto`
   (`presupuestos/service.py:41-88`) calcula lo mismo pero excluyendo los ítems con
   `excluido=True`, un campo que Pricing no conoce. Si la regla de negocio de qué
   cuenta como "ítem vigente" cambiara, habría que modificar dos archivos sin
   relación de código de forma consistente — mismo patrón de riesgo que
   `catalogo`/`imports/service.py` con el versionado de costo
   (`../catalogo/pendientes.md` P2(1)).

2. **Reimplementación independiente de la condición de vigencia de costo.**
   [IMPLEMENTADO]. `pricing/repository.py:55-64`
   (`buscar_costo_estandar_vigente`) usa `fecha_hasta IS NULL` como condición de
   vigencia — la misma que `catalogo.repository.costo_vigente`
   (`catalogo/repository.py:137-146`), sin código compartido entre ambas. Menos
   grave que el caso de `imports/service.py` con el versionado completo (documentado
   en [`../catalogo/pendientes.md`](../catalogo/pendientes.md) P2(1)), porque acá es
   solo una lectura, no una regla de escritura duplicada — pero es el mismo patrón
   de acoplamiento de tabla sin abstracción compartida.

3. **Sin transacción explícita entre el `DELETE` y el `INSERT` de
   `presupuesto_items` en una regeneración.** [IMPLEMENTADO]. `service.py:275`
   (`DELETE`) y `service.py:307-308` (`INSERT`) son dos llamadas HTTP separadas a
   PostgREST, sin ninguna envoltura transaccional a nivel de aplicación. Si el
   proceso falla entre ambas (timeout, caída del servicio), el presupuesto queda
   con `presupuesto_items` vacío pero con los totales ya actualizados en
   `presupuestos` — mismo patrón de riesgo ya señalado para
   [`../catalogo/decisiones.md`](../catalogo/decisiones.md) D-CATALOGO-002. No es
   un bug reproducido en esta sesión, es una hipótesis razonable a partir de la
   lectura del código.

4. **Un ítem sin `producto_id` resuelto desaparece silenciosamente del
   presupuesto.** [IMPLEMENTADO] (RN-PRICING-007). `buscar_items_con_producto`
   filtra por `producto_id NOT NULL` (`repository.py:163`) — un ítem del proceso
   comercial que todavía no fue matcheado a un producto no genera ninguna fila en
   `presupuesto_items`, ni aparece como `sin_precio`, ni se refleja en
   `cantidad_items`. Un usuario mirando el presupuesto generado no tiene, desde
   este módulo, ninguna señal de que hay ítems del proceso original que quedaron
   completamente fuera del cálculo — a diferencia de un ítem `sin_precio` (que sí
   aparece, con `precio_unitario=None`). Riesgo funcional de que un presupuesto
   parezca "completo" (por ejemplo, `items_sin_precio == 0`) cuando en realidad
   faltan ítems enteros sin matchear.

## P3 — Menor

1. **`GET /precios-especiales` es el único endpoint de todo el módulo (y uno de
   los pocos del proyecto) que bypasea `service.py`.** [IMPLEMENTADO]
   (D-PRICING-004). `router.py:43-48` consulta
   `v_precios_especiales_vigentes` directo con `user_client`, rompiendo la
   consistencia arquitectónica del resto de `presupuestacion/`, donde los routers
   delegan siempre en `service.py`. Sin test de integración dedicado en
   `tests/pricing/test_service.py` (los 7 tests existentes cubren únicamente
   `generar_presupuesto`).

2. **Sin guarda contra división por cero al calcular `margen_resultante_pct`.**
   [IMPLEMENTADO] (RN-PRICING-009). `service.py:156` divide por `costo` sin
   chequear que sea mayor a cero, a diferencia de
   `presupuestos.ajustar_item` (`presupuestos/service.py:153-157`), que sí lo hace
   para el mismo cálculo. No reproducido como bug en esta sesión — depende de que
   `costos_productos.costo_unitario` o `precios_proveedor.precio_unitario` admitan
   `0`, algo no verificable sin acceso al schema.

3. **`DetalleCalculo.muestras` se propaga pero no se usa en ningún cálculo ni
   validación.** [IMPLEMENTADO]. `service.py:74` copia `mercado.get("muestras")` al
   detalle persistido, pero ningún punto del módulo valida un mínimo de muestras
   antes de confiar en la mediana de mercado — una mediana calculada sobre una sola
   oferta pesa igual que una calculada sobre cien. Pendiente de definición
   funcional si esto es intencional.

4. **Cobertura de test parcial de las ramas de la cascada.** [IMPLEMENTADO] la
   ausencia. Los 7 tests de `tests/pricing/test_service.py` cubren: margen objetivo
   sin mercado, precio especial vs. estándar, mercado gana al piso, piso gana al
   mercado, sin precio por falta de costo, sin precio por falta de regla, y
   regeneración sin huérfanos. No hay test para: alcance específico de una regla
   por `cliente_id`/`clase_proceso`/`categoria_id` (RN-PRICING-004, siempre se
   siembra una regla con alcance `NULL` en los 3 campos), `clase_proceso ==
   "licitacion"` (para confirmar `stock_verificado is False`, RN-PRICING-005),
   `margen_objetivo_pct IS NULL` sin mercado (para confirmar el `sin_precio` con
   regla presente, RN-PRICING-006), ni un ítem con `producto_id IS NULL`
   (RN-PRICING-007).

No se detectó código muerto: las funciones de `repository.py` y `service.py` tienen
al menos un call site dentro del propio módulo o son ejercitadas directo por
`tests/pricing/test_service.py` (confirmado leyendo ambos archivos completos en
esta sesión).
