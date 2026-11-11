# Specification: Agente de interpretación de formatos para Comparativas

Palabras clave según RFC 2119. Las decisiones DEC-n están en `proposal.md`.

## Contrato público

- `procesar_comparativa(ruta_archivo, nombre_original, *, session_id, drogueria_id, instrucciones_extra)`
  MUST conservar su firma y seguir devolviendo el `Path` del CSV.
- `POST /procesar` MUST NOT cambiar su contrato HTTP.
- Con `COMPARATIVAS_AGENTE=off` el sistema MUST comportarse como antes de este cambio.

## Extracción

### Requisito: sin pérdida silenciosa

El sistema MUST NOT entregar un resultado incompleto como si fuera completo.

- **Given** una comparativa en la que un bloque no pudo extraerse tras los reintentos
  **When** termina el procesamiento
  **Then** la extracción queda en `partial` y las advertencias identifican los renglones o páginas
  afectados.

- **Given** una respuesta truncada del modelo
  **When** el extractor la detecta
  **Then** divide el bloque de forma recursiva hasta un renglón, y cada parte conserva encabezados
  y lista de proveedores.

### Requisito: resultado completo (DEC-3)

- El extractor MUST guardar todas las ofertas con precio válido, no solo las 3 más baratas.
- El extractor MUST NOT aplicar filtros ni órdenes de carácter comercial.
- El orden por precio y cualquier límite de cantidad MUST vivir en `presupuestacion`.

- **Given** un renglón con 7 proveedores que cotizan
  **When** se procesa la comparativa
  **Then** el resultado contiene las 7 ofertas y la pantalla de validación puede mostrarlas todas.

### Requisito: análisis de estructura

- Antes de extraer, el sistema MUST producir un `PerfilEstructura` del documento.
- Si la huella estructural coincide con un formato conocido y activo, el sistema SHOULD reutilizar
  su perfil sin llamar al modelo.
- El corte en bloques MUST usar el patrón de renglón del perfil y MUST NOT separar un renglón de
  sus proveedores.

- **Given** una comparativa con renglones identificados como "R1", "R2"
  **When** se divide en bloques
  **Then** cada bloque empieza en un renglón completo y ningún renglón queda repartido.

## Prompt dinámico

- El prompt MUST componerse en este orden: reglas base, estructura del documento, instrucciones del
  cliente, lecciones validadas, ejemplos, avisos.
- Las reglas base MUST NOT modificarse en tiempo de ejecución.
- Solo lecciones en estado `validada` MAY inyectarse.
- Cada extracción MUST registrar la versión del prompt base y los ids de formato y lecciones usados.

- **Given** un formato con una lección `candidata` y otra `validada`
  **When** se construye el prompt
  **Then** solo aparece la `validada`.

- **Given** una lección que contradice una regla base
  **When** se construye el prompt
  **Then** prevalece la regla base y el conflicto queda registrado en la traza.

## Validación del resultado

- El sistema MUST validar en código, sin IA: cobertura de renglones, duplicados, esquema, anclaje al
  texto fuente, proveedores fuera de lista, escala de precio y desplazamiento.
- Cada problema MUST identificar bloque y renglón.

- **Given** un precio que no aparece en el texto fuente de su bloque
  **When** corre el validador de anclaje
  **Then** se registra una advertencia para ese renglón y proveedor.

- **Given** un documento con renglones 1 a 40 y un resultado sin el 17
  **When** corre el validador de cobertura
  **Then** se registra un error que nombra el renglón 17 y su bloque.

## Reproceso

- El sistema MUST reprocesar solo los bloques con problemas.
- El sistema MUST NOT superar 2 rondas de reproceso por bloque.
- El reproceso MUST incluir en el prompt el problema detectado.

- **Given** una comparativa de 10 bloques con un error de cobertura en el bloque 4
  **When** se dispara el reproceso
  **Then** solo se vuelve a llamar al modelo para el bloque 4.

## Memoria de formatos

- Todas las tablas de memoria MUST llevar `drogueria_id` y RLS por droguería (DEC-1).
- La recuperación MUST seguir este orden: formato del cliente, huella exacta, similitud.
- Una recuperación por similitud por debajo del umbral MUST devolver vacío.
- Los ejemplos guardados MUST NOT contener precios, marcas ni proveedores reales.
- Las correcciones crudas MUST NOT inyectarse en ningún prompt de extracción.

- **Given** dos droguerías con el mismo formato de comparativa
  **When** una de ellas aprueba una lección
  **Then** la otra no la recibe.

- **Given** un cliente con `cliente_formato_documentos` activo
  **When** se procesa su comparativa
  **Then** sus instrucciones se incluyen en el prompt, como hoy.

## Aprendizaje

- Al validar una comparativa, el sistema MUST guardar la diferencia entre las filas extraídas y las
  confirmadas, también cuando no hay cambios.
- Una lección MUST nacer en estado `candidata`.
- Solo un usuario con la capacidad `formatos.lecciones.aprobar` MAY pasarla a `validada` (DEC-2).
- El sistema MUST NOT crear conocimiento a partir de extracciones no validadas (DEC-6).
- Una instrucción que contenga valores con forma de precio o nombres de proveedores o clientes MUST
  rechazarse antes de guardarse.

- **Given** una extracción validada con correcciones en la columna marca
  **When** corre el proceso de aprendizaje
  **Then** se crea una lección `candidata` asociada al formato, y no se usa en ningún prompt hasta
  su aprobación.

- **Given** una extracción que nadie validó
  **When** corre el proceso de aprendizaje
  **Then** no se genera ninguna lección ni ejemplo a partir de ella.

## Impacto en el flujo de datos

| Tramo | Antes | Después |
|---|---|---|
| Parseo | Un string de Markdown | Bloques con procedencia (páginas, hoja, rango de renglones) |
| Extracción | Prompt genérico por chunk | Prompt por capas por bloque |
| Resultado | CSV con top 3 | JSON completo con advertencias, más CSV con todas las ofertas |
| Estado | `completed` aunque falten datos | `partial` con advertencias cuando falta algo |
| Validación | Filas corregidas se materializan | Además se guarda la diferencia |
| Materialización | Recibe 3 ofertas por renglón | Recibe todas y calcula posiciones |

## Archivos

| Archivo | Estado |
|---|---|
| `services/extraccion/comparativas_agente/*` | Nuevo |
| `services/extraccion/robot_comparativas.py` | Modificado: fachada |
| `services/extraccion/parsers.py` | Modificado: bloques con procedencia y correcciones de parseo |
| `services/extraccion/persistent_output.py` | Modificado: guarda `resultado_path` |
| `services/presupuestacion/extraccion/{service,repository,models,router}.py` | Modificado: advertencias y diferencia al validar |
| `services/shared/permisos.py` | Modificado: capacidades de lecciones |
| `frontend/src/features/validar-extraccion/` | Modificado: todas las ofertas y advertencias |
| `frontend/src/features/formatos-lecciones/` | Nuevo: aprobación de lecciones |
| `supabase/migrations/00NN_*.sql` + `.down.sql` | Nuevo: tablas y columnas de la sección 4 de design.md |
| `docs/schema/extractor_final.sql`, `docs/schema/rls_final.sql` | Modificado |
| `docs/modulos/extraccion_ia/`, `docs/ia/README.md` | Modificado |
| `scripts/medir_comparativas.py` | Nuevo |
