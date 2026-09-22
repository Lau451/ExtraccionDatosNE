# Especificación: Candidato de presupuesto para matching de orden de compra

## Purpose

Dada una orden de compra ya validada y confirmada, con su `cliente_id` resuelto, encontrar y
rankear los presupuestos de ese cliente contra los cuales conviene reconciliar los renglones de la
OC, para que el usuario elija con cuál trabajar antes de vincular renglón a renglón.

## Requirements

### Requirement: Ranking de presupuestos del cliente por coincidencia exacta de precio

El sistema MUST listar los presupuestos que pertenecen al `cliente_id` ya confirmado de la orden de
compra. Para cada presupuesto listado, el sistema MUST calcular un puntaje igual a la cantidad de
renglones de la OC cuyo `precio_unitario` coincide de forma exacta, sin tolerancia, con el
`precio_unitario` de al menos un renglón de ese presupuesto (`presupuesto_items.precio_unitario`).
El sistema MUST ordenar los presupuestos candidatos de mayor a menor puntaje, mostrando primero el
de más coincidencias.

#### Scenario: Un presupuesto tiene más coincidencias exactas que los demás

- GIVEN un cliente con tres presupuestos, donde uno de ellos comparte precio unitario exacto con
  más renglones de la OC que los otros dos
- WHEN el usuario abre la pantalla de candidatos para esa orden de compra
- THEN el presupuesto con más coincidencias exactas aparece primero en la lista

#### Scenario: Ningún renglón de la OC coincide en precio con un presupuesto dado

- GIVEN un presupuesto del cliente cuyos renglones no comparten ningún precio unitario exacto con
  los renglones de la OC
- WHEN se calcula el ranking de candidatos
- THEN ese presupuesto aparece en la lista con puntaje cero, sin excluirse automáticamente de las
  opciones

### Requirement: Selección explícita del presupuesto por el usuario

El sistema MUST presentar el ranking como sugerencia, nunca como una elección automática: el
presupuesto contra el cual se va a vincular la OC MUST ser el que el usuario seleccionó
explícitamente en pantalla, incluso cuando hay un único presupuesto candidato o uno con puntaje
notablemente más alto que el resto.

#### Scenario: Un solo presupuesto candidato igual requiere selección explícita

- GIVEN un cliente con un único presupuesto cargado
- WHEN el usuario abre la pantalla de candidatos
- THEN el sistema lo muestra como único candidato sugerido, pero el vínculo renglón a renglón no
  arranca hasta que el usuario lo selecciona explícitamente

### Requirement: Estado explícito cuando el cliente no tiene presupuestos cargados

Si el `cliente_id` de la orden de compra no tiene ningún presupuesto asociado, el sistema MUST
mostrar un estado explícito de "sin presupuestos para este cliente", MUST NOT tratarlo como un
error, y MUST permitir que la orden de compra siga existiendo con sus renglones sin vincular.

#### Scenario: Cliente sin presupuestos cargados

- GIVEN una orden de compra cuyo cliente no tiene presupuestos cargados en el sistema
- WHEN el usuario abre la pantalla de candidatos para esa orden de compra
- THEN el sistema muestra un estado explícito de ausencia de presupuestos, no un error
- AND la orden de compra permanece disponible para revisarse más adelante, cuando exista un
  presupuesto contra el cual matchear
