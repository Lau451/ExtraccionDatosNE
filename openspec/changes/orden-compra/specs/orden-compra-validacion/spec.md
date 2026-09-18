# Especificación: Validación de orden de compra

## Purpose

Confirmar una extracción de tipo `orden_compra` materializándola en `ordenes_compra`/`oc_items`/
`entregas_oc`, anclada a un cliente que el usuario confirma explícitamente a partir de una
sugerencia en varios niveles, y dividida en entregas. Cuando la orden de compra llegó repartida en
varios archivos, esta validación reconcilia sus filas en una sola sesión antes de confirmar.

## Requirements

### Requirement: Sugerencia de cliente en niveles, con confirmación humana siempre obligatoria

El sistema MUST sugerir un cliente para anclar la orden de compra evaluando, en orden y con
cortocircuito, las siguientes fuentes: (1) un alias de cliente aprendido de confirmaciones
anteriores para el mismo texto de cabecera; (2) el CUIT extraído del documento, buscado entre los
clientes existentes. Si ninguna fuente resuelve, el sistema MUST permitir al usuario buscar el
cliente manualmente. Ninguna fuente MUST anclar la orden de compra por sí sola: el `cliente_id`
que se persiste al confirmar es siempre el que el usuario confirmó explícitamente en pantalla,
sin excepción — incluso cuando la sugerencia es una única coincidencia exacta.

Una búsqueda por CUIT MUST poder devolver más de un cliente candidato cuando ese CUIT es
compartido legítimamente por varias cuentas (por ejemplo, sedes distintas bajo el CUIT de un
organismo). En ese caso el sistema MUST presentar la lista de candidatos para que el usuario
elija, en lugar de tratarlo como un error de ambigüedad.

#### Scenario: Sugerencia por alias aprendido

- GIVEN el texto de cabecera del documento coincide exactamente, tras normalizar, con un alias
  aprendido de una confirmación anterior
- WHEN el usuario abre la pantalla de validación
- THEN el sistema sugiere ese cliente, preseleccionado pero sin confirmar
- AND la confirmación de la orden de compra sigue requiriendo el click explícito del usuario

#### Scenario: Sugerencia por CUIT con un único candidato

- GIVEN el CUIT extraído del documento corresponde a un único cliente
- WHEN no hay alias aprendido que coincida
- THEN el sistema sugiere ese cliente como candidato único, sin anclarlo automáticamente

#### Scenario: CUIT compartido por varios clientes

- GIVEN el CUIT extraído del documento corresponde a varias cuentas de cliente distintas que
  comparten ese CUIT de forma legítima
- WHEN no hay alias aprendido que coincida
- THEN el sistema presenta la lista de candidatos para que el usuario elija uno
- AND esto MUST NOT tratarse como un error ni bloquear la pantalla

#### Scenario: Sin sugerencia disponible

- GIVEN ni el alias aprendido ni el CUIT extraído resuelven a ningún cliente
- WHEN el usuario abre la pantalla de validación
- THEN el sistema no bloquea ni reporta error: el usuario busca el cliente manualmente entre los
  clientes existentes

#### Scenario: Confirmación humana obligatoria en todos los casos

- GIVEN cualquier origen de sugerencia (alias, CUIT único, CUIT compartido, o búsqueda manual)
- WHEN el usuario no hizo click explícito de confirmación sobre un cliente
- THEN la orden de compra MUST NOT poder confirmarse

#### Scenario: `cliente_id` confirmado inválido

- GIVEN un `cliente_id` que no existe, no corresponde a un cliente, o pertenece a otra droguería
- WHEN el usuario intenta confirmar la orden de compra con ese `cliente_id`
- THEN el sistema MUST rechazar la confirmación con un error explícito antes de escribir
  cualquier dato

### Requirement: Aprendizaje del alias de cliente a partir de cada confirmación

Cuando el usuario confirma un cliente para un texto de cabecera dado, el sistema MUST registrar
(o actualizar) un alias que asocia ese texto normalizado con el cliente confirmado, de forma que
una futura orden de compra con el mismo texto de cabecera lo sugiera automáticamente en el nivel
más alto de confianza. Si el texto ya tenía un alias registrado a otro cliente, la confirmación
más reciente MUST reemplazar la asociación anterior.

#### Scenario: Primera confirmación de un texto de cabecera nuevo

- GIVEN un texto de cabecera que nunca fue confirmado antes
- WHEN el usuario confirma un cliente para esa orden de compra
- THEN el sistema registra un alias nuevo que asocia ese texto con el cliente confirmado

#### Scenario: Corrección de un alias existente

- GIVEN un texto de cabecera con un alias ya registrado a un cliente distinto
- WHEN el usuario confirma un cliente diferente para ese mismo texto
- THEN el sistema actualiza el alias para que apunte al cliente recién confirmado

### Requirement: Reconciliación de filas cuando la orden de compra llegó en varios archivos

Cuando una orden de compra fue agrupada a partir de varios archivos, el sistema MUST mostrar en
una sola sesión de validación las filas de todos los archivos del grupo, concatenadas tal como
salieron de cada extracción, sin fusionar, deduplicar ni sumar cantidades automáticamente entre
archivos. El número de línea que haya traído el documento original, si lo trae, MUST mostrarse
solo como referencia visual junto con el archivo de origen de cada fila, para que el usuario
reconozca a simple vista qué filas de distintos archivos corresponden a la misma línea. Ese
número de línea del documento MUST NOT usarse para fusionar o descartar filas automáticamente.
La reconciliación de filas duplicadas o repetidas entre archivos (por ejemplo, la misma línea
repetida con distinta fecha de entrega) queda a cargo del usuario, editando o eliminando filas
antes de confirmar.

El sistema MUST permitir agrupar, después de la carga, extracciones de orden de compra que se
subieron por separado, y MUST permitir deshacer una agrupación existente. Ambas operaciones MUST
NOT ser posibles sobre una extracción que ya fue validada.

#### Scenario: Filas de un grupo se muestran concatenadas, sin fusión automática

- GIVEN una orden de compra agrupada a partir de 3 archivos
- WHEN el usuario abre la pantalla de validación
- THEN ve las filas de los 3 archivos concatenadas, cada una identificada con su archivo de
  origen, sin ninguna fila fusionada o sumada automáticamente

#### Scenario: El número de línea del documento es solo de referencia

- GIVEN dos filas de archivos distintos del mismo grupo que traen el mismo número de línea
  declarado por el documento
- WHEN el usuario visualiza la tabla de validación
- THEN ambas filas se muestran por separado, con su número de línea como dato de solo lectura, sin
  bloquear ni advertir automáticamente por la coincidencia

#### Scenario: El usuario reconcilia filas duplicadas manualmente

- GIVEN un grupo cuyo segundo archivo repite las líneas del primero con una fecha de entrega
  distinta
- WHEN el usuario decide que esas filas no deben duplicarse
- THEN puede eliminar o editar las filas necesarias antes de confirmar, usando las mismas acciones
  de edición de filas que ya existen en la pantalla

#### Scenario: Agrupar extracciones sueltas después de la carga

- GIVEN dos o más extracciones de orden de compra sin validar, subidas por separado
- WHEN el usuario las selecciona y pide agruparlas
- THEN el sistema las asocia como un solo grupo y sus filas pasan a mostrarse concatenadas en una
  sola sesión de validación

#### Scenario: No se puede agrupar una extracción ya validada

- GIVEN una extracción de orden de compra que ya fue confirmada
- WHEN el usuario intenta incluirla en una agrupación
- THEN el sistema MUST rechazar la operación

#### Scenario: Desagrupar

- GIVEN un grupo de extracciones de orden de compra sin validar
- WHEN el usuario pide desagruparlas
- THEN cada extracción vuelve a comportarse como independiente

### Requirement: Cabecera conciliada entre los archivos de un grupo

Cuando los archivos de un grupo declaran datos de cabecera distintos entre sí (número de orden de
compra, CUIT, razón social, fecha de emisión, dirección de entrega, cantidad de entregas), el
sistema MUST presentar una única cabecera editable para todo el grupo, precargada con el valor más
frecuente entre los archivos. Una discrepancia en el número de orden de compra MUST bloquear la
confirmación hasta que el usuario la resuelva, porque identifica de forma unívoca a la orden de
compra. Una discrepancia en cualquier otro campo de cabecera MUST NOT bloquear la confirmación:
el sistema advierte la discrepancia y deja que el usuario la corrija si corresponde.

#### Scenario: Número de orden de compra discrepante bloquea la confirmación

- GIVEN un grupo cuyos archivos declaran números de orden de compra distintos entre sí
- WHEN el usuario intenta confirmar sin resolver la discrepancia
- THEN el sistema MUST bloquear la confirmación

#### Scenario: Otros campos de cabecera discrepantes solo advierten

- GIVEN un grupo cuyos archivos declaran fechas de emisión o direcciones de entrega distintas
  entre sí
- WHEN el usuario abre la pantalla de validación
- THEN el sistema muestra el valor más frecuente precargado y marca la discrepancia como
  advertencia, sin impedir que el usuario confirme

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

#### Scenario: Reparto parejo por conteo de entregas

- GIVEN el documento solo indica la cantidad de entregas, sin desglose por línea
- WHEN el sistema reparte la cantidad de cada línea entre las entregas
- THEN el reparto MUST ser lo más parejo posible: para cantidades enteras, la diferencia entre la
  entrega con más unidades y la que tiene menos MUST ser como máximo 1 unidad, y ese excedente se
  concentra en las primeras entregas del cronograma
- AND la suma de las cantidades repartidas entre todas las entregas de una línea MUST ser
  exactamente igual a la cantidad total de esa línea, sin fracciones no entregables

### Requirement: Materialización al confirmar

Confirmar una orden de compra MUST crear filas en `ordenes_compra`, `oc_items` y `entregas_oc`
(esquema `compras`, no las tablas de presupuesto/comparativa). `proceso_comercial_id` es nullable en
esta ruta; `cliente_id` MUST fijarse con el valor que el usuario confirmó explícitamente en
pantalla (ver Requirement de sugerencia de cliente), nunca con un valor resuelto
automáticamente. El CHECK `proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL` MUST
cumplirse siempre.

El número de línea persistido en `oc_items` MUST ser asignado por el sistema como un ordinal
secuencial (1, 2, 3, ...) sobre el conjunto final de filas que el usuario confirmó, en el orden en
que quedaron en la pantalla al momento de confirmar. El sistema MUST NOT persistir el número de
línea tal como vino del documento ni del payload enviado por el usuario: ese número, cuando existe,
cumplió su función como referencia visual durante la validación y se descarta al confirmar. Esto
aplica exactamente igual a una orden de compra de un solo archivo que a una agrupada.

Cuando la orden de compra fue agrupada a partir de varios archivos, confirmar MUST materializar
una única orden de compra a partir del conjunto de filas ya reconciliado, y MUST marcar como
validados todos los archivos que integran el grupo, no solo el que el usuario abrió.

#### Scenario: Confirmación exitosa

- GIVEN una orden de compra válida, con cliente y entregas definidas
- WHEN el usuario confirma
- THEN se crean las filas correspondientes en `ordenes_compra`, `oc_items` y `entregas_oc`

#### Scenario: Confirmar no descuenta stock

- GIVEN una orden de compra recién confirmada
- WHEN termina la confirmación
- THEN el stock MUST NOT cambiar y `entregas_oc` queda con cantidades pendientes, no entregadas

#### Scenario: El número de línea persistido es siempre un ordinal del sistema

- GIVEN una orden de compra con 4 filas confirmadas, donde el documento no declaró número de línea
  en ninguna
- WHEN el usuario confirma
- THEN `oc_items` queda con números de línea 1, 2, 3 y 4 asignados por el sistema en el orden final
  de las filas, sin que la ausencia del dato en el documento bloquee ni afecte la confirmación

#### Scenario: Confirmar una orden de compra agrupada valida todo el grupo

- GIVEN una orden de compra agrupada a partir de 2 archivos, con sus filas ya reconciliadas por el
  usuario
- WHEN el usuario confirma
- THEN se crea una única orden de compra a partir de las filas reconciliadas
- AND ambos archivos del grupo quedan marcados como validados

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
