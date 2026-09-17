# Especificación: Importación de entregas

## Purpose

Importar el CSV de retorno de Progress con las cantidades efectivamente entregadas, actualizando
`entregas_oc`/`entregas_oc_items` y descontando stock — este es el único momento en que el stock se
mueve en todo el flujo de orden de compra.

## Requirements

### Requirement: Importación del CSV de retorno de Progress

El usuario MUST importar manualmente el CSV exportado por Progress con cantidades entregadas. El
sistema MUST actualizar cantidades entregadas/pendientes por línea y por entrega en
`entregas_oc`/`entregas_oc_items`, reutilizando sin cambios el mecanismo existente `crear_entrega`
→ `entregar_stock_producto`.

#### Scenario: Importación actualiza entregado y descuenta stock

- GIVEN un CSV de retorno con cantidades entregadas por línea
- WHEN el usuario lo importa
- THEN se actualizan las cantidades entregadas/pendientes y se descuenta el stock correspondiente

#### Scenario: Cumplimiento parcial de una entrega (UNRESOLVED)

- GIVEN el CSV reporta menos cantidad que la esperada para una entrega
- WHEN se procesa la importación
- THEN la semántica exacta y el `estado` resultante de esa entrega quedan UNRESOLVED, diferidos a
  diseño (Open Question #2 de la propuesta)
