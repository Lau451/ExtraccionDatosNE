# Delta for Validación de orden de compra

## ADDED Requirements

### Requirement: Navegación automática a la pantalla de matching tras confirmar

Al confirmar exitosamente la validación de una extracción de tipo `orden_compra`, el resultado
devuelto MUST incluir el `orden_compra_id` de la orden recién creada. El frontend MUST navegar
automáticamente, inmediatamente después de la confirmación, a la pantalla de matching
OC↔presupuesto de esa misma orden de compra, en lugar de volver al listado de extracciones.

Para extracciones de otro tipo (`licitacion`, `comparativa`), `orden_compra_id` MUST ser `null` y
el comportamiento de navegación existente para esas rutas MUST NOT cambiar.

El contrato de tipos del frontend para el resultado de validación MUST reflejar todos los campos
que el backend ya devuelve para esta operación (incluyendo `orden_compra_id`,
`entregas_creadas`, `renglones_sin_producto` y `extracciones_validadas`), no solo el subconjunto
que reflejaba antes de este cambio.

#### Scenario: Confirmar una orden de compra navega a la pantalla de matching

- GIVEN un usuario confirmando una extracción de tipo `orden_compra` válida
- WHEN la confirmación se completa con éxito
- THEN el resultado incluye `orden_compra_id` con el id de la orden de compra recién creada
- AND el frontend navega automáticamente a la pantalla de matching de esa orden de compra, sin
  pasar por el listado de extracciones

#### Scenario: Confirmar una licitación o comparativa no cambia su navegación

- GIVEN un usuario confirmando una extracción de tipo `licitacion` o `comparativa`
- WHEN la confirmación se completa con éxito
- THEN `orden_compra_id` en el resultado es `null`
- AND el comportamiento de navegación de esa ruta permanece igual al que tenía antes de este
  cambio

#### Scenario: El contrato de tipos del frontend refleja los campos ya devueltos por el backend

- GIVEN que el modelo de resultado del backend ya devuelve `orden_compra_id`,
  `entregas_creadas`, `renglones_sin_producto` y `extracciones_validadas`
- WHEN el frontend consume el resultado de una validación
- THEN su interfaz de TypeScript declara los cuatro campos, no solo el subconjunto que declaraba
  antes de este cambio
