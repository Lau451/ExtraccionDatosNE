# Especificación: Exportación de nota de pedido

## Purpose

Generar y exportar en CSV la nota de pedido de una orden de compra confirmada, para su importación
manual en Progress v8 (el descuento de stock en Progress ocurre en ese momento, no acá).

## Requirements

### Requirement: Exportación de nota de pedido en CSV

El sistema MUST permitir exportar como CSV la nota de pedido de una `orden_compra` confirmada. El
formato exacto de columnas del CSV queda fuera de este spec (decisión pendiente de diseño).

#### Scenario: Exportación de OC confirmada

- GIVEN una orden de compra confirmada
- WHEN el usuario solicita exportar su nota de pedido
- THEN el sistema genera un CSV descargable

#### Scenario: Exportación bloqueada si no está confirmada

- GIVEN una orden de compra aún no confirmada
- WHEN el usuario intenta exportar su nota de pedido
- THEN el sistema MUST impedir la exportación
