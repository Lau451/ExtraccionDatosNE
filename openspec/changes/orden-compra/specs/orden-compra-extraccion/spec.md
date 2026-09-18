# Especificación: Extracción de orden de compra

## Purpose

Clasificar y extraer documentos de orden de compra (PDF/imagen/Excel/HTML) como tercer tipo de
documento soportado, junto a `presupuesto`/`comparativa`, persistiendo el resultado en
`extraction_results`. Una orden de compra puede llegar repartida en varios archivos: el sistema
MUST permitir agruparlos bajo una identidad de grupo compartida al momento de la carga.

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

### Requirement: Agrupación de archivos al momento de la carga

Una orden de compra puede llegar repartida en N archivos separados (por ejemplo, N entregas
declaradas en N documentos distintos). El sistema MUST aceptar un identificador de grupo opcional
en cada llamada de carga, de forma que N archivos subidos con el mismo identificador queden
asociados como una sola orden de compra lógica. Cada archivo MUST seguir extrayéndose y
persistiéndose de forma independiente, con su propio CSV en disco; el identificador de grupo solo
asocia las filas de `extraction_results` entre sí, sin fusionar ni combinar los archivos en
ningún paso de la extracción. La ausencia del identificador de grupo MUST comportarse exactamente
igual que hoy: una extracción independiente y sin asociación a ninguna otra.

#### Scenario: Carga de N archivos como un solo grupo

- GIVEN un usuario sube 3 archivos que corresponden a la misma orden de compra
- WHEN cada carga se envía con el mismo identificador de grupo
- THEN las 3 filas resultantes en `extraction_results` quedan asociadas entre sí como un solo
  grupo
- AND cada una conserva su propio CSV en disco sin modificar

#### Scenario: Carga de un solo archivo sin agrupar

- GIVEN un usuario sube un único archivo de orden de compra sin identificador de grupo
- WHEN el servicio de extracción lo procesa
- THEN el comportamiento es idéntico al de una extracción sin capacidad de agrupación

#### Scenario: Identificador de grupo inválido

- GIVEN un usuario envía un identificador de grupo que no tiene la forma esperada
- WHEN el servicio de extracción recibe la carga
- THEN el sistema MUST rechazar el valor inválido sin afectar el resto de la carga

#### Scenario: Archivo duplicado dentro de un grupo

- GIVEN dos de los archivos que el usuario intenta agrupar son idénticos byte a byte
- WHEN se sube el segundo archivo duplicado
- THEN el sistema MUST rechazarlo como duplicado sin abortar los demás archivos del grupo
- AND el grupo queda formado con los archivos que sí se procesaron

### Requirement: El `numero_renglon` extraído nunca se fabrica

Cuando el documento declara un número de línea por renglón, el extractor MUST incluirlo tal cual
aparece en el documento. Cuando el documento NO declara ningún número de línea, el sistema MUST
dejar ese campo vacío y MUST NOT derivarlo, inferirlo, autoincrementarlo ni completarlo de ninguna
otra forma. Un valor vacío en este campo es un resultado válido y MUST NOT hacer fallar la
extracción.

#### Scenario: Documento que declara número de línea

- GIVEN un documento de orden de compra que numera explícitamente cada renglón
- WHEN se extrae el documento
- THEN cada fila del CSV conserva el número de línea tal como aparece en el documento

#### Scenario: Documento que no declara número de línea

- GIVEN un documento de orden de compra que no numera sus renglones de ninguna forma
- WHEN se extrae el documento
- THEN el campo de número de línea queda vacío en todas las filas del CSV
- AND la extracción MUST NOT fallar ni bloquearse por esa ausencia
