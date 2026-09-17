# Especificación: Validación de orden de compra

## Purpose

Confirmar una extracción de tipo `orden_compra` materializándola en `ordenes_compra`/`oc_items`/
`entregas_oc`, anclada a un cliente por `codigo_interno` y dividida en entregas.

## Requirements

### Requirement: Anclaje a cliente por `codigo_interno`

El usuario MUST ingresar manualmente el `codigo_interno` durante la validación. El sistema MUST
buscar el cliente correspondiente y fijar `cliente_id` con el resultado.

#### Scenario: Cliente encontrado

- GIVEN un `codigo_interno` con una única coincidencia
- WHEN el usuario lo ingresa
- THEN el sistema asocia ese cliente a la orden de compra

#### Scenario: `codigo_interno` ambiguo

- GIVEN que `clientes.codigo_interno` no tiene restricción de unicidad y existen varias coincidencias
- WHEN el usuario intenta confirmar
- THEN el sistema MUST bloquear la confirmación hasta resolver la ambigüedad

#### Scenario: `codigo_interno` sin coincidencia

- GIVEN que ningún cliente coincide con el código ingresado
- WHEN el usuario intenta confirmar
- THEN el sistema MUST impedir la confirmación y mostrar un error explícito

### Requirement: División en entregas

El sistema MUST usar las entregas extraídas del documento (cantidad, plazo en días, a veces por
línea) cuando estén presentes. Cuando no se detecten, el usuario MUST ingresarlas manualmente. La
confirmación MUST NOT proceder sin al menos una entrega definida.

#### Scenario: Entregas extraídas del documento

- GIVEN el documento declara cantidades por línea y por entrega
- WHEN se valida la extracción
- THEN el sistema crea las filas de `entregas_oc` con esos valores

#### Scenario: Entregas no detectadas

- GIVEN el documento no declara ninguna entrega
- WHEN el usuario intenta confirmar sin haber cargado al menos una
- THEN el sistema MUST bloquear la confirmación

#### Scenario: Reparto parejo por conteo de entregas (UNRESOLVED)

- GIVEN el documento solo indica la cantidad de entregas, sin desglose por línea
- WHEN el sistema reparte la cantidad de cada línea entre las entregas
- THEN el reparto MUST ser lo más parejo posible; la regla exacta para el resto cuando la división
  no es exacta queda UNRESOLVED, diferida a diseño (Open Question #1 de la propuesta)

### Requirement: Materialización al confirmar

Confirmar una orden de compra MUST crear filas en `ordenes_compra`, `oc_items` y `entregas_oc`
(esquema `compras`, no las tablas de presupuesto/comparativa). `proceso_comercial_id` es nullable en
esta ruta; `cliente_id` MUST fijarse desde el lookup por `codigo_interno`. El CHECK
`proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL` MUST cumplirse siempre.

#### Scenario: Confirmación exitosa

- GIVEN una orden de compra válida, con cliente y entregas definidas
- WHEN el usuario confirma
- THEN se crean las filas correspondientes en `ordenes_compra`, `oc_items` y `entregas_oc`

#### Scenario: Confirmar no descuenta stock

- GIVEN una orden de compra recién confirmada
- WHEN termina la confirmación
- THEN el stock MUST NOT cambiar y `entregas_oc` queda con cantidades pendientes, no entregadas

### Requirement: Unicidad de `numero_oc` por ruta de anclaje

El sistema MUST aplicar unicidad de `numero_oc`+`version_numero` scoped a
`(drogueria_id, cliente_id)` para OC ancladas a cliente, y scoped a
`(drogueria_id, proceso_comercial_id)` para OC ancladas solo por proceso comercial, mediante dos
índices únicos parciales independientes.

#### Scenario: Mismo `numero_oc`, clientes distintos

- GIVEN dos clientes distintos de la misma droguería
- WHEN ambos registran una OC con el mismo `numero_oc`/`version_numero`
- THEN ambas confirmaciones MUST tener éxito

#### Scenario: Mismo `numero_oc`, mismo cliente

- GIVEN un cliente con una OC existente bajo ese `numero_oc`/`version_numero`
- WHEN se intenta confirmar otra con el mismo par
- THEN el sistema MUST rechazar la confirmación con un error de conflicto
