# Proposal: Agente de interpretación de formatos para Comparativas

> Estado: **propuesta aprobada, sin implementar**. Este cambio solo agrega documentos en
> `openspec/changes/comparativas-agente-formatos/`. No se modificó código.
>
> Relación con otros cambios: reemplaza la parte de comparativas de
> `openspec/changes/parser-router-comparatives-refactor` (la extracción en dos pasos que ahí se
> propone queda absorbida por el analizador de estructura de este cambio).

## Intent

La extracción de comparativas depende hoy de un único prompt genérico
(`_PROMPT_UNIFIED`, `services/extraccion/robot_comparativas.py:64`). Con archivos largos o de
estructura compleja falla seguido, y cuando falla no avisa.

El objetivo es que el módulo pase a tener una capa que, antes de extraer:

1. interpreta la estructura del documento,
2. recupera lo que ya se aprendió de formatos parecidos,
3. arma el prompt con instrucciones específicas para ese documento,
4. valida el resultado con reglas en código,
5. reprocesa solo el bloque que falló,
6. aprende de las correcciones que el usuario confirma al validar.

## Estado actual (verificado en el código)

| Paso | Dónde | Qué hace |
|---|---|---|
| Entrada | `services/extraccion/main.py` (`POST /procesar`) | Lanza `procesar_comparativa` en background |
| Parseo | `services/extraccion/parsers.py` | Convierte a Markdown: pdfplumber → Docling → Gemini Vision; pandas para Excel |
| Formato por cliente | `main.py:_resolver_formato_prompt`, tabla `cliente_formato_documentos` | Concatena al prompt instrucciones cargadas a mano por cliente |
| Extracción | `robot_comparativas.py` | Un prompt, chunks de 15 renglones o 15 páginas, 3 llamadas en paralelo |
| Filtro | `robot_comparativas.py:_filtrar_top_3_por_renglon` | Deja los 3 proveedores más baratos por renglón |
| Salida | CSV `renglon;proveedor;marca;precio;cliente` | Se guarda en disco y se registra en `extraction_results` |
| Validación | `services/presupuestacion/extraccion/service.py:validar_extraccion` | El usuario corrige filas (`filas_override`) y se materializa en `comparativas` / `ofertas_items` |

## Limitaciones que este cambio ataca

1. **Prompt ciego a la estructura.** El mismo texto para proveedores en columnas, en filas o en
   bloques por proveedor.
2. **Chunks sin contexto global.** Cada chunk redescubre proveedores y encabezados.
   `_split_chunk_in_half` (`robot_comparativas.py:452`) deja el contexto solo en la primera mitad.
3. **Pérdida silenciosa.** Un chunk que falla se reemplaza por un resultado vacío
   (`robot_comparativas.py:555` y `:723`) y el CSV sale incompleto sin aviso. En PDFs de más de 20
   páginas no hay manejo de truncamiento (`:664`).
4. **Heurística frágil de renglón.** "Primera celda numérica" (`:327`) no reconoce "R1",
   "Renglón 1" ni "1.1", y confunde cantidades con renglones.
5. **Sin validación del resultado.** Nada comprueba cobertura, desplazamiento de columnas ni datos
   inventados.
6. **Las correcciones no dejan conocimiento.** `filas_override` se materializa, pero la diferencia
   con lo extraído no se guarda.
7. **El extractor aplica una regla comercial.** El top 3 por precio vive en el extractor y descarta
   datos antes de que alguien pueda validarlos.
8. **Pérdidas en el parseo.** `_extract_native_pdf` descarta el texto de páginas con tablas;
   `_distribute_brands` asume columnas fijas 1/3/5; `_parse_excel` lee solo la primera hoja;
   `is_scanned_pdf` muestrea 3 páginas.

## Decisiones tomadas

| ID | Decisión | Origen |
|---|---|---|
| DEC-1 | La memoria de formatos es **por droguería**. No se comparte entre droguerías. Compartir patrones entre droguerías queda como decisión posterior. | Confirmado por el dueño del producto |
| DEC-2 | Las lecciones las aprueban **admin y líder comercial**, al menos al principio. | Confirmado |
| DEC-3 | El **top 3 sale del extractor**. La extracción guarda todos los proveedores que cotizan y la pantalla de validación puede mostrar más de 3. | Confirmado |
| DEC-4 | El "agente" es un **orquestador en Python con pasos fijos**. Gemini interviene en tres puntos: análisis de estructura, extracción y propuesta de lecciones. No se incorpora un framework de agentes. | Recomendación técnica |
| DEC-5 | No se entrena un modelo propio. Solo memoria, recuperación y prompt dinámico. | Pedido original |
| DEC-6 | Nada entra en la memoria sin validación humana. Las extracciones del propio sistema nunca se usan como conocimiento. | Pedido original |

## Scope

### Nuevo

- Paquete `services/extraccion/comparativas_agente/` (analizador, memoria, prompt_builder,
  extractor, validadores, orquestador, aprendizaje).
- Tablas `formatos_documento`, `formato_lecciones`, `formato_ejemplos`,
  `extraccion_correcciones` y columnas de traza en `processing_sessions`.
- Set de referencia de comparativas reales con resultado esperado y script de medición.
- Pantalla de aprobación de lecciones y advertencias en la pantalla de validación.

### Modificado

- `services/extraccion/robot_comparativas.py`: queda como fachada con la misma firma
  `procesar_comparativa(...)`.
- `services/presupuestacion/extraccion/`: guarda la diferencia al validar, expone advertencias y
  aplica el orden por precio al materializar.
- `frontend/src/features/validar-extraccion/`: muestra todos los proveedores que cotizan y las
  advertencias por renglón.

### Sin cambios

- `robot.py` (licitaciones) y `robot_orden_compra.py`.
- Motor de precios, matching y reglas comerciales.
- Contrato HTTP de `POST /procesar`.
- `cliente_formato_documentos`: se conserva y pasa a ser el primer nivel de la memoria.

## Tecnologías

| Tecnología | Estado | Uso en este cambio |
|---|---|---|
| Gemini API (`google-genai`) | En uso | Análisis de estructura, extracción, propuesta de lecciones, embeddings |
| Docling, pdfplumber, PyMuPDF, pypdf | En uso | Parseo y señales de estructura. Sin cambios de dependencia |
| Python + FastAPI | En uso | Lógica del agente. No se crea un servicio nuevo |
| Supabase (Postgres + RLS) | En uso | Tablas de memoria con `drogueria_id` |
| pgvector | **No habilitado** (las migraciones solo activan `pgcrypto` y `pg_cron`) | Similitud entre formatos. Recién en la etapa 3 |

## Etapas

| Etapa | Contenido | Resultado medible |
|---|---|---|
| 0. Base | Set de referencia, fin de las pérdidas silenciosas, resultado completo persistido, top 3 fuera del extractor | Línea de base de precisión |
| 1. Estructura | Analizador y prompt por capas, reutilizando el formato por cliente | Mejora en formatos complejos |
| 2. Validación | Validadores, reproceso por bloque, advertencias en pantalla | Ningún CSV incompleto sin aviso |
| 3. Memoria | Tablas, huella estructural, luego pgvector | Formatos repetidos sin análisis desde cero |
| 4. Aprendizaje | Captura de correcciones, lecciones candidatas, aprobación | Menos correcciones por formato en el tiempo |

La etapa 0 es condición del resto: sin el set de referencia no se puede medir si el agente mejora,
y sin el resultado completo las correcciones solo ven el top 3.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Más filas en validación: con todos los proveedores se supera `MAX_FILAS_EDITABLES = 500` (`presupuestacion/extraccion/models.py:11`) en comparativas grandes | Resolver en la etapa 0: paginar o agrupar por renglón en la pantalla. Ver design.md, punto abierto PA-1 |
| Costo y latencia: una llamada de análisis por documento más los reprocesos | Análisis sobre una muestra, no sobre el documento entero; máximo 2 rondas de reproceso; se omite el análisis si la huella coincide con un formato conocido |
| Una lección mala degrada extracciones futuras | Solo lecciones aprobadas; traza de qué lección usó cada extracción; métrica de acierto por lección y retiro |
| Fuga de datos comerciales por la memoria | Al prompt solo llegan perfiles, lecciones y ejemplos con valores sintéticos. Las correcciones crudas nunca se inyectan |
| El validador de anclaje da falsos positivos (precios reformateados por el parser) | Comparar valores normalizados; arrancar en modo advertencia, no bloqueante |

## Rollback

- Cada etapa entra detrás de una variable de entorno (`COMPARATIVAS_AGENTE=off|on`). Con `off`,
  `procesar_comparativa` usa el flujo actual.
- Las migraciones son aditivas (tablas y columnas nuevas, todas con `.down.sql`). Ninguna modifica
  ni borra columnas existentes.
- El CSV actual se sigue generando durante la transición, así que `presupuestacion` puede volver a
  leerlo sin cambios.
- La mudanza del top 3 (DEC-3) es el único cambio de comportamiento visible para el usuario. Se
  revierte reactivando el filtro en la fachada.
