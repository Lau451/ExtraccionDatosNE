# Especificación: Extracción de orden de compra

## Purpose

Clasificar y extraer documentos de orden de compra (PDF/imagen/Excel/HTML) como tercer tipo de
documento soportado, junto a `presupuesto`/`comparativa`, persistiendo el resultado en
`extraction_results`.

## Requirements

### Requirement: Reconocimiento del tipo `orden_compra`

El sistema MUST aceptar `tipo == "ordenes"` en el endpoint de carga y extraerlo con un extractor
Gemini dedicado. El sistema MUST NOT devolver HTTP 422 para este tipo.

#### Scenario: Carga válida de orden de compra

- GIVEN un usuario sube un documento con `tipo=ordenes`
- WHEN el servicio de extracción lo procesa
- THEN se crea una fila en `extraction_results` con `document_type=orden_compra` y sin error 422

#### Scenario: Ya no se rechaza de antemano

- GIVEN el comportamiento previo devolvía 422 fijo para `tipo=="ordenes"`
- WHEN se repite la misma carga tras este cambio
- THEN el sistema MUST intentar la extracción real en lugar de rechazarla de antemano
