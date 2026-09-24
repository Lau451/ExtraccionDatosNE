# Especificación: Vinculación de renglones de orden de compra contra presupuesto

## Purpose

Dentro del presupuesto elegido para una orden de compra, vincular cada renglón de la OC con el
renglón de presupuesto que le corresponde, para heredar el `producto_id` ya resuelto del lado del
presupuesto. El precio exacto es la clave de vínculo, la similitud de descripción es solo el
desempate, y la confirmación humana es siempre la compuerta final — ningún vínculo se aplica sin un
click explícito del usuario, en ningún nivel de confianza.

## Requirements

### Requirement: Sugerencia de vínculo por precio exacto, con desempate por descripción

Para cada renglón de la orden de compra, el sistema MUST buscar, dentro del presupuesto elegido,
los renglones cuyo `precio_unitario` coincide de forma exacta y sin tolerancia con el
`precio_unitario` del renglón de la OC.

- Si hay exactamente un renglón de presupuesto con ese precio, el sistema MUST mostrarlo como
  sugerencia única para ese renglón de OC.
- Si hay más de un renglón de presupuesto con el mismo precio, el sistema MUST ordenar esos
  candidatos por similitud de descripción (reutilizando `rapidfuzz` y `normalizar_descripcion`, los
  mismos mecanismos ya usados por el motor de matching de productos existente) y presentarlos como
  lista ordenada, MUST NOT preseleccionar ninguno de ellos.
- Si ningún renglón de presupuesto comparte ese precio, el renglón de la OC MUST quedar en estado
  `pendiente`.

#### Scenario: Un único match de precio se sugiere sin vincularse

- GIVEN un renglón de OC cuyo precio unitario coincide de forma exacta con un único renglón del
  presupuesto elegido
- WHEN el usuario abre la pantalla de vinculación
- THEN el sistema muestra ese renglón de presupuesto como sugerencia para el renglón de OC
- AND el vínculo MUST NOT quedar aplicado hasta que el usuario lo confirme con un click

#### Scenario: Varios matches del mismo precio se ordenan por similitud de descripción

- GIVEN un renglón de OC cuyo precio unitario coincide de forma exacta con más de un renglón del
  presupuesto elegido, con descripciones distintas
- WHEN el usuario abre la pantalla de vinculación
- THEN el sistema muestra esos candidatos ordenados por similitud de descripción respecto del
  renglón de OC
- AND ninguno de los candidatos aparece preseleccionado

#### Scenario: Renglón de OC sin ningún match de precio

- GIVEN un renglón de OC cuyo precio unitario no coincide con ningún renglón del presupuesto
  elegido
- WHEN se calculan las sugerencias de vínculo
- THEN ese renglón de OC queda marcado como `pendiente`

#### Scenario: Caso validado con datos reales — dos renglones sin ambigüedad

- GIVEN una orden de compra con 2 renglones cuyos precios unitarios coinciden, cada uno de forma
  exacta con un renglón distinto de un mismo presupuesto, sin que ningún otro renglón del
  presupuesto comparta esos precios
- WHEN se calculan las sugerencias de vínculo
- THEN cada renglón de OC recibe exactamente un renglón de presupuesto sugerido, sin ambigüedad y
  sin necesidad de desempate por descripción

### Requirement: Confirmación humana obligatoria y granular por renglón

Ningún vínculo MUST aplicarse de forma automática, sin importar el nivel de confianza de la
sugerencia. El sistema MUST permitir confirmar cada renglón de OC de forma individual, en el
momento en que el usuario lo decide, sin exigir que se confirmen todos los renglones antes de
aplicar cualquiera de ellos.

#### Scenario: Confirmar un renglón no exige confirmar los demás primero

- GIVEN una orden de compra con varios renglones, cada uno con su propia sugerencia de vínculo
- WHEN el usuario confirma el vínculo de un solo renglón
- THEN ese vínculo queda aplicado
- AND los demás renglones permanecen sin cambios, disponibles para confirmarse en cualquier
  momento posterior

#### Scenario: Ningún vínculo se aplica sin click explícito

- GIVEN un renglón de OC con una sugerencia de vínculo, única o desempatada por descripción
- WHEN el usuario no hizo click explícito de confirmación sobre esa sugerencia
- THEN el vínculo MUST NOT quedar aplicado

### Requirement: Herencia de `producto_id` al confirmar un vínculo

Confirmar el vínculo de un renglón de OC contra un renglón de presupuesto MUST copiar el
`producto_id` del renglón de presupuesto al renglón de OC correspondiente.

#### Scenario: Confirmar un vínculo hereda el producto

- GIVEN un renglón de OC con una sugerencia de vínculo confirmable contra un renglón de
  presupuesto que tiene `producto_id` resuelto
- WHEN el usuario confirma el vínculo
- THEN el `producto_id` del renglón de OC queda igual al `producto_id` del renglón de presupuesto
  vinculado

### Requirement: Estado `pendiente` no bloqueante

Un renglón de OC en estado `pendiente` MUST NOT impedir que el usuario confirme los vínculos de
los demás renglones de la misma orden de compra, y MUST NOT impedir que la sesión de vinculación
se considere utilizable con renglones pendientes.

#### Scenario: Renglones pendientes conviven con renglones confirmados

- GIVEN una orden de compra donde algunos renglones quedaron `pendiente` y otros tienen
  sugerencia de vínculo
- WHEN el usuario confirma los vínculos de los renglones con sugerencia
- THEN esas confirmaciones se aplican con normalidad
- AND los renglones `pendiente` siguen visibles como tales, sin bloquear la sesión

### Requirement: Relación N:1 permitida, con aviso no bloqueante

Un renglón de presupuesto MUST poder quedar vinculado desde más de un renglón de OC. El sistema
MUST permitir esta reutilización sin bloquearla y MUST mostrar un aviso no bloqueante cuando el
usuario confirma un vínculo hacia un renglón de presupuesto que ya está vinculado desde otro
renglón de OC.

#### Scenario: Vincular un segundo renglón de OC al mismo renglón de presupuesto

- GIVEN un renglón de presupuesto ya vinculado desde un renglón de OC
- WHEN el usuario confirma el vínculo de otro renglón de OC distinto contra ese mismo renglón de
  presupuesto
- THEN el sistema MUST permitir la confirmación
- AND MUST mostrar un aviso no bloqueante indicando que ese renglón de presupuesto ya está
  vinculado

### Requirement: `items_proceso.estado_matching` y `confianza_matching` quedan fuera de alcance

El sistema MUST NOT leer ni escribir `items_proceso.estado_matching` ni
`items_proceso.confianza_matching` en ningún paso del ranking de candidatos, la sugerencia de
vínculos, o la confirmación. Esos campos pertenecen al motor de matching de productos contra
catálogo, que es un concepto distinto y no se toca.

#### Scenario: Una sesión completa de vinculación no modifica los campos del otro motor

- GIVEN una orden de compra con renglones vinculados, pendientes y reutilizados en relación N:1
- WHEN se completa una sesión de vinculación de principio a fin
- THEN `items_proceso.estado_matching` y `items_proceso.confianza_matching` quedan exactamente
  igual que antes de la sesión, para todos los renglones involucrados
