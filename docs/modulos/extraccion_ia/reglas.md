# Reglas — Extracción IA (legacy)

Todas las reglas fueron verificadas contra el código real (`robot.py`,
`robot_comparativas.py`, `parsers.py`, `config.py`, `gemini_errors.py`) y sus tests
(`tests/test_limpiar_cantidad.py`, `tests/test_robot_comparativas.py`,
`tests/test_brand_distribution.py`, `tests/test_fallback.py`) en esta sesión.

### RN-EXTRACCIONIA-001 — Formato de salida esperado para licitaciones/pedidos: CSV con 4 columnas fijas

- **Descripción**: el prompt de `robot.py` exige a Gemini devolver únicamente CSV, con
  `;` como separador, encabezado incluido, sin comillas y con el campo `origen` forzado
  al nombre del cliente derivado del archivo.
- **Condición**: cualquier llamada a `procesar_archivo` (Excel o "documento" genérico).
- **Resultado**: prompt literal (`robot.py:312-326`):

  > "Analiza este {tipo_doc} y extrae la informacion solicitada en formato CSV. ...
  > CAMPOS: item;cantidad;descripcion;origen ... REGLAS: - Devuelve SOLO CSV - Usa
  > punto y coma (;) - Incluye encabezado - Una fila por producto - Sin texto adicional
  > - No uses comillas - El campo origen debe ser exactamente: {cliente}"

  Si el archivo es Excel, se antepone una nota de estructura (cabecera a ignorar +
  tabla a extraer, `robot.py:304-308`) y se aplican `instrucciones_extra` del cliente si
  existen (`robot.py:328-329`, §8 formato por cliente).
- **Prioridad**: Alta.
- **Archivo**: `robot.py:268-360` (`procesar_archivo`).
- **Observaciones**: [IMPLEMENTADO]. La respuesta se valida de forma mínima: se exige
  que `"item;"` aparezca en el texto en minúsculas (`robot.py:341-342`), si no aparece
  se levanta `ValueError("Respuesta invalida (no es CSV)")` — no hay validación de
  esquema más estricta (número de columnas, tipos) antes de escribir el archivo.

### RN-EXTRACCIONIA-002 — Formato de salida esperado para comparativas: JSON estructurado con `proveedores` y `renglones`

- **Descripción**: `_PROMPT_UNIFIED` exige a Gemini un JSON con la lista de
  proveedores detectados y, por cada renglón, un mapa `proveedor → {precio, marca}`.
- **Condición**: cualquier llamada a `_llamar_gemini_json` (usada tanto en el flujo de
  chunking por Markdown como en el de chunking por páginas de PDF).
- **Resultado**: prompt literal (`robot_comparativas.py:64-98`, resumen fiel):

  > "Extract data from this price comparison document ... Return ONLY valid JSON: {
  > "proveedores": [...], "renglones": [{"renglon": N, "proveedores_precios": {"Provider
  > A": {"precio": "...", "marca": "..."}}}] } ... RULES: - "marca": brand name only, no
  > catalog codes (PM/C. numbers). Use "sin marca" if no brand is found - "precio": unit
  > price as a number string, empty string if provider does not quote - "proveedor":
  > full provider name. Use "sin proveedor" if name cannot be determined - Include ALL
  > providers for every renglon, even those that don't quote - Return ALL items found"

  La llamada fuerza `response_mime_type="application/json"` y `max_output_tokens=65_536`
  vía `_JSON_CONFIG` (`robot_comparativas.py:47-50`, comentario: "gemini-2.5-flash max;
  prevents mid-JSON truncation").
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:64-98` (prompt), `:122-169` (`_llamar_gemini_json`).
- **Observaciones**: [IMPLEMENTADO]. Si Gemini responde con una lista en vez de un dict,
  `_llamar_gemini_json` infiere la estructura si los elementos tienen clave `"renglon"`,
  o devuelve una estructura vacía en caso contrario (`robot_comparativas.py:160-167`).

### RN-EXTRACCIONIA-003 — Umbral de chunking por caracteres para el flujo Markdown de comparativas

- **Descripción**: si el Markdown comprimido supera `_CHUNK_THRESHOLD` caracteres, se
  divide en chunks de `_CHUNK_SIZE` ítems cada uno antes de llamar a Gemini.
- **Condición**: `len(markdown) > _CHUNK_THRESHOLD` (40.000 caracteres).
- **Resultado**: `_split_markdown_chunks(markdown)` con `chunk_size=15` ítems por
  default; si no se supera el umbral, se procesa en un único chunk.
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:52-53` (`_CHUNK_THRESHOLD = 40_000`,
  `_CHUNK_SIZE = 15`), `:515` (aplicación de la condición dentro de
  `_extraer_comparativa`).
- **Observaciones**: [IMPLEMENTADO]. El comentario junto a `_CHUNK_SIZE` dice
  "reduce to 10 if truncation persists in Phase 3" (`robot_comparativas.py:53`) —
  evidencia de que el valor 15 fue ajustado empíricamente y podría requerir
  recalibración futura; no hay lógica automática que lo reduzca dinámicamente. Verificado
  con `tests/test_robot_comparativas.py:378-405`
  (`test_extraer_comparativa_usa_chunking_para_markdown_grande`,
  `test_extraer_comparativa_no_usa_chunking_para_markdown_pequeno`).

### RN-EXTRACCIONIA-004 — Umbral de chunking por páginas para PDFs grandes

- **Descripción**: si un PDF de comparativa supera `_PDF_PAGE_THRESHOLD` páginas, se usa
  el flujo de chunking por páginas (en vez del flujo Markdown-completo) — split del PDF
  con `pypdf`, parseo y extracción Gemini por chunk, en paralelo.
- **Condición**: `total_pages > _PDF_PAGE_THRESHOLD` (20 páginas), verificado antes de
  parsear el documento completo (`robot_comparativas.py:959-966`).
- **Resultado**: `_extraer_comparativa_por_paginas`, con chunks de
  `_PAGE_CHUNK_SIZE=15` páginas y `_PAGE_OVERLAP=1` página de solapamiento entre chunks
  consecutivos, para que los ítems que caen en un borde de página aparezcan completos en
  al menos un chunk.
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:56-58` (constantes), `:580-626`
  (`_split_pdf_by_pages`), `:650-729` (`_extraer_comparativa_por_paginas`).
- **Observaciones**: [IMPLEMENTADO]. Si falla el conteo de páginas (excepción al abrir
  el PDF con `pypdf`), se degrada silenciosamente al flujo Markdown-completo con un
  `logger.warning` (`robot_comparativas.py:965-966`) — no hay test directo de esa rama
  de fallo (ver [`pendientes.md`](./pendientes.md)).

### RN-EXTRACCIONIA-005 — Criterio de truncamiento: `finish_reason=MAX_TOKENS` o JSON inválido

- **Descripción**: antes de parsear la respuesta de Gemini como JSON, se revisa
  `finish_reason` del primer candidato. Si contiene `"MAX_TOKENS"`, o si el `json.loads`
  falla, se levanta `GeminiTruncationError` — un error **determinístico**, marcado
  explícitamente como "no reintentable con el mismo input".
- **Condición**: `"MAX_TOKENS" in finish_reason` (chequeado antes de parsear) o
  `json.JSONDecodeError` al parsear `response.text`.
- **Resultado**: `GeminiTruncationError` con el largo de la respuesta y el
  `finish_reason` en el mensaje.
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:138-158` (`_llamar_gemini_json`),
  `gemini_errors.py:34-44` (clase `GeminiTruncationError`, docstring: "This error is
  DETERMINISTIC — retrying the exact same input will produce the same truncation. ...
  Never retry this with the same chunk."), `gemini_errors.py:84-85` (el decorador
  `handle_gemini_errors` re-levanta `GeminiTruncationError` sin reintentar: `except
  GeminiTruncationError: raise  # deterministic`).
- **Observaciones**: [IMPLEMENTADO]. Ver RN-EXTRACCIONIA-006 para qué hace el caller con
  este error (split-in-half, no reintento simple).

### RN-EXTRACCIONIA-006 — Manejo de truncamiento: split-in-half automático del chunk

- **Descripción**: cuando `_llamar_gemini_json` levanta `GeminiTruncationError` para un
  chunk, `_process_chunk` lo divide en 2 mitades por cantidad de ítems
  (`_split_chunk_in_half`) y procesa cada mitad por separado, mezclando los resultados.
- **Condición**: `GeminiTruncationError` capturado en `_process_chunk`.
- **Resultado**: si el chunk tiene ≤1 ítem, no se puede dividir más — se registra un
  `logger.warning` y se devuelve `{"proveedores": [], "renglones": []}` (pérdida
  silenciosa de ese chunk). Si se puede dividir, cada mitad se procesa con una llamada
  independiente a `_llamar_gemini_json` (sin recursión adicional de split — si una mitad
  vuelve a truncarse, esa segunda `GeminiTruncationError` **no** se captura de nuevo en
  este nivel y se propaga).
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:411-454` (`_split_chunk_in_half`), `:457-488`
  (`_process_chunk`).
- **Observaciones**: [IMPLEMENTADO]. `_split_chunk_in_half` opera sobre la estructura de
  tabla Markdown con separador `|`, agrupando filas por ítem igual que
  `_split_markdown_chunks` — no aplica al flujo de chunking por páginas de PDF
  (`_procesar_chunk_pdf` no llama a `_process_chunk`, llama directo a
  `_llamar_gemini_json` sin split-in-half, `robot_comparativas.py:629-647`) — ver
  [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONIA-007 — Fallback entre modelos Gemini ante cualquier excepción

- **Descripción**: `generate_with_fallback` intenta primero `PRIMARY_MODEL`
  (`gemini-2.5-flash`); si la llamada levanta **cualquier** excepción, reintenta una vez
  con `FALLBACK_MODEL` (`gemini-3-flash-preview`), sin inspeccionar el tipo ni el
  mensaje de la excepción original.
- **Condición**: `except Exception as exc` genérico (`config.py:102`) — no distingue
  errores de cuota, autenticación, red, timeout o cualquier otro.
- **Resultado**: segunda llamada a `client.models.generate_content(model=FALLBACK_MODEL,
  ...)`, con un `logger.warning` que menciona ambos modelos.
- **Prioridad**: Alta.
- **Archivo**: `config.py:96-105`.
- **Observaciones**: [IMPLEMENTADO], confirmado además por
  `tests/test_fallback.py:30-63` (`test_usa_fallback_cuando_primario_falla`,
  `test_fallback_con_rate_limit`, `test_fallback_con_timeout` — los 3 tests usan
  excepciones de naturaleza distinta y verifican el mismo comportamiento de fallback sin
  discriminar). No hay ningún test que verifique el comportamiento ante un error de
  **autenticación** del modelo primario (API key inválida) — el código tal como está
  también reintentaría con el modelo fallback en ese caso, reutilizando el mismo cliente
  (y por lo tanto la misma API key potencialmente inválida). Ver
  [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONIA-008 — Reintentos con backoff diferenciado por tipo de error clasificado

- **Descripción**: `handle_gemini_errors` clasifica cada excepción por palabras clave en
  el mensaje (`_classify_gemini_error`) y aplica una política de reintento distinta
  según la clase resultante.
- **Condición** (evaluada en orden, `gemini_errors.py:55-66`):
  - Contiene `quota`, `exhausted`, `resource_exhausted` o `out of quota` →
    `GeminiQuotaExceededError`.
  - Si no, contiene `rate limit`, `too many requests`, `429`, `deadline exceeded`,
    `503`, `high demand` o `unavailable` → `GeminiRateLimitError`.
  - Cualquier otra excepción → `GeminiAPIError` genérico.
- **Resultado**:
  - `GeminiQuotaExceededError` → **no se reintenta**, se relanza de inmediato
    (`gemini_errors.py:100-102`).
  - `GeminiRateLimitError` → backoff exponencial `wait = (2 ** attempt) *
    backoff_factor` segundos, hasta `max_retries` intentos (`gemini_errors.py:104-117`).
  - Cualquier otro error (incluida `GeminiAPIError` genérica) → backoff lineal corto
    `wait = 1.0 * (attempt + 1)` segundos, también hasta `max_retries`
    (`gemini_errors.py:119-131`).
- **Prioridad**: Alta.
- **Archivo**: `gemini_errors.py:55-136` (`_classify_gemini_error`,
  `handle_gemini_errors`). Aplicado con `max_retries=4, backoff_factor=40.0` en
  `robot.py:267` (`procesar_archivo`) y `robot_comparativas.py:122`
  (`_llamar_gemini_json`).
- **Observaciones**: [IMPLEMENTADO]. Con `backoff_factor=40.0` y `max_retries=4`, un
  error clasificado como rate-limit persistente espera `40s, 80s, 160s` en los intentos
  1, 2 y 3 antes de fallar definitivamente en el intento 4 (sin espera adicional) — ver
  D-EXTRACCIONIA-003 en [`decisiones.md`](./decisiones.md) sobre por qué esos valores no
  están justificados con un comentario en el código. La clasificación se hace por texto
  del mensaje de excepción (`str(e).lower()`), no por tipo de excepción — cualquier
  error cuyo mensaje mencione, por ejemplo, "503" será tratado como rate-limit aunque su
  causa real sea otra.

### RN-EXTRACCIONIA-009 — Fuzzy matching de columnas Excel por similitud de texto normalizado

- **Descripción**: `_normalizar_excel` identifica las columnas `item`, `cantidad` y
  `descripcion` de un Excel arbitrario comparando el nombre normalizado de cada columna
  contra listas de sinónimos, con un umbral de similitud.
- **Condición**: para cada columna candidata, se normaliza (minúsculas, sin acentos, sin
  caracteres no alfanuméricos, `_normalizar_texto`, `robot.py:38-44`) y se compara: 1.0
  si coincide exacto con un sinónimo, 0.85 si un sinónimo está contenido en el nombre (o
  viceversa), o el ratio de `SequenceMatcher` en caso contrario. Se toma la columna con
  mayor score; se acepta solo si `score >= umbral` (0.72 por default).
- **Resultado**: si no se encuentra columna de `cantidad`/`descripcion` por sinónimos, se
  intenta una segunda pasada por contenido de los datos: `_score_cantidad` (ratio de
  valores convertibles a número) y `_score_descripcion` (ratio de valores de texto con
  ≥3 caracteres), aceptando la mejor columna candidata si su score es `>= 0.6`. Si no
  hay columna de `item`, se genera una secuencia incremental `range(1, len(df)+1)`.
- **Prioridad**: Media.
- **Archivo**: `robot.py:38-71` (`_normalizar_texto`, `_mejor_match_columna`),
  `:74-104` (`_score_cantidad`, `_score_descripcion`, `_col_to_series`), `:191-260`
  (`_normalizar_excel`).
- **Observaciones**: [IMPLEMENTADO]. No hay test unitario de `_normalizar_excel` ni de
  `_mejor_match_columna` en el repositorio (confirmado: solo `test_limpiar_cantidad.py`
  cubre `robot.py`, y no incluye estas funciones) — ver
  [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONIA-010 — Limpieza de cantidad: formato argentino vs. formato inglés

- **Descripción**: `_limpiar_cantidad` trunca la columna `cantidad` de la respuesta CSV
  al entero, resolviendo ambigüedad entre separador decimal (coma, formato AR) y
  separador de miles (punto).
- **Condición** (aplicada en orden por celda, `robot.py:120-137`):
  1. Si hay `,` → todo lo posterior a la primera coma se descarta (decimal AR:
     `4.750,00` → `4.750`).
  2. Si hay exactamente un `.` y la parte entera tiene ≥4 dígitos → se interpreta como
     decimal inglés y se descarta la parte decimal (`4750.000` → `4750`).
  3. Se eliminan todos los `.` restantes (separador de miles AR: `1.500` → `1500`).
- **Resultado**: valor entero como string, sin separadores.
- **Prioridad**: Alta.
- **Archivo**: `robot.py:107-140` (`_limpiar_cantidad`).
- **Observaciones**: [IMPLEMENTADO], con cobertura completa de casos límite en
  `tests/test_limpiar_cantidad.py` (comas decimales, puntos de miles, combinación de
  ambos, sin columna `cantidad`, CSV vacío — 12 casos parametrizados + 4 tests
  adicionales, todos verificados en esta sesión).

### RN-EXTRACCIONIA-011 — Limpieza de precio: soporte multi-formato (AR/US/símbolos de moneda)

- **Descripción**: `_limpiar_precio` normaliza un string de precio arbitrario a formato
  numérico con 2 decimales, o `""` si no es interpretable.
- **Condición** (aplicada en orden, `robot_comparativas.py:195-223`):
  1. Vacío o coincide con marcadores de "no cotiza" (`-`, `n/a`, `no cotiza`, `sin
     precio`, `s/p`) → `""`.
  2. Se eliminan símbolos de moneda (`$`, `€`, espacios, `USD`, `ARS`).
  3. Si tiene `,` **y** `.` → formato argentino/europeo: se elimina el `.` (miles) y la
     `,` se convierte en `.` (decimal): `1.234,56` → `1234.56`.
  4. Si tiene solo `,` → se convierte a `.`: `12,34` → `12.34`.
  5. Si tiene más de un `.` → el último es el decimal, el resto se eliminan (miles):
     `8.100.00000` → `8100.00000`.
  6. Se intenta `float(cleaned)`; si falla, se logea un `warning` y se devuelve `""`.
- **Resultado**: string numérico con 2 decimales (`f"{value:.2f}"`), o `""`.
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:172-225` (`_limpiar_precio`).
- **Observaciones**: [IMPLEMENTADO], con 20 casos parametrizados en
  `tests/test_robot_comparativas.py:53-91` (vacíos, formato AR, formato US, símbolos de
  moneda, cero, espacios, no numérico), todos verificados en esta sesión.

### RN-EXTRACCIONIA-012 — Filtro de comparativas: top 3 proveedores por renglón, ordenados por precio ascendente

- **Descripción**: `_filtrar_top_3_por_renglon` agrupa todos los precios de un mismo
  renglón (deduplicando entre chunks solapados), descarta proveedores sin precio válido
  y conserva únicamente los 3 más baratos.
- **Condición**: por cada renglón, se arma una lista `(proveedor, precio_limpio, marca,
  precio_num)` solo con precios que pasan `_limpiar_precio` sin quedar vacíos; si no
  queda ningún proveedor con precio válido, el renglón entero se descarta con un
  `logger.warning`.
- **Resultado**: lista ordenada ascendente por precio, recortada a los primeros 3
  (`provider_price_list.sort(...)`, `top_3 = provider_price_list[:3]`,
  `robot_comparativas.py:802-803`). Si falta el número de renglón, se asigna uno
  incremental basado en la posición (`robot_comparativas.py:757-758`).
- **Prioridad**: Alta.
- **Archivo**: `robot_comparativas.py:732-823` (`_filtrar_top_3_por_renglon`).
- **Observaciones**: [IMPLEMENTADO], con 11 tests dedicados en
  `tests/test_robot_comparativas.py:146-249` (máximo 3 por renglón, orden ascendente,
  omisión de proveedores sin precio, renglón sin ningún precio válido, renglón
  incremental, formato legacy de precio como string plano, inclusión de marca,
  sanitización de `;` en todos los campos, múltiples renglones independientes).

### RN-EXTRACCIONIA-013 — Detección de PDF escaneado por densidad de texto nativo

- **Descripción**: `is_scanned_pdf` decide si un PDF es "escaneado" (sin texto nativo,
  solo imagen) muestreando páginas con PyMuPDF antes de cualquier procesamiento pesado.
- **Condición**: de las primeras `sample_pages` páginas (3 por default), se cuenta
  cuántas tienen más de 50 caracteres de texto extraído (`doc[i].get_text()`); si la
  proporción de páginas "con texto" es `< 0.5`, se considera escaneado.
- **Resultado**: `True` (escaneado) o `False` (nativo). Si PyMuPDF no está instalado,
  siempre devuelve `False` (asume nativo) — `parsers.py:44-49`, `:205-206`.
- **Prioridad**: Media.
- **Archivo**: `parsers.py:196-218` (`is_scanned_pdf`).
- **Observaciones**: [IMPLEMENTADO]. No hay test directo de esta función en el
  repositorio (confirmado por grep en `tests/` en esta sesión, sin resultados) — ver
  [`pendientes.md`](./pendientes.md).

### RN-EXTRACCIONIA-014 — Cadena de fallback de `_parse_pdf`: pdfplumber nativo → Docling → Vision

- **Descripción**: ver el diagrama completo en [`arquitectura.md`](./arquitectura.md).
  Resumen de la regla: se prioriza la extracción más barata (pdfplumber, sin llamada a
  IA) para PDFs nativos, se reserva Docling (ML local, más costoso en RAM) para PDFs
  escaneados o cuando pdfplumber falla/devuelve vacío, y Gemini Vision (llamada a API de
  pago) queda como último recurso cuando Docling no está instalado o falla.
- **Condición**: ver `parsers.py:511-522` (docstring) y `:524-596` (implementación).
- **Resultado**: string Markdown/texto, sin importar cuál handler lo produjo — el
  caller no puede distinguir por cuál rama pasó salvo leyendo los logs
  (`pipeline=native_pdf|docling_native_fallback|docling_scanned|vision_fallback`,
  emitidos en `_extract_native_pdf:430-433` y `_parse_pdf:575-581`, `:586`).
- **Prioridad**: Alta.
- **Archivo**: `parsers.py:511-597` (`_parse_pdf`).
- **Observaciones**: [IMPLEMENTADO]. Gran parte de esta cadena **no tiene test
  directo** — confirmado por grep en `tests/` en esta sesión: no hay ningún test que
  importe o mockee `_parse_pdf`, `_parse_excel`, `_parse_html`, `_parse_image`,
  `is_scanned_pdf` o `_extract_native_pdf`. La única cobertura indirecta de este archivo
  son `_clean_brand` y `_distribute_brands` (`tests/test_brand_distribution.py`), que son
  helpers internos de `_extract_native_pdf`, no la función completa ni la cadena de
  fallback. Ver [`pendientes.md`](./pendientes.md) P1.

### RN-EXTRACCIONIA-015 — `_distribute_brands` asume un layout de columnas fijo

- **Descripción**: `_distribute_brands` redistribuye una celda de Descripción
  multilínea (con varias marcas separadas por `\n`, producto de cómo pdfplumber fusiona
  celdas en comparativas) a las filas de precio individuales de cada proveedor.
- **Condición**: el propio docstring declara el layout asumido — "Column layout assumed:
  0=Proveedor, 1=Item, 3=Descripción, 5=PU" (`parsers.py:278`), materializado como
  constantes `ITEM_COL=1, DESC_COL=3, PRICE_COL=5` (`parsers.py:280-282`).
- **Resultado**: si la tabla extraída por pdfplumber no respeta ese layout exacto (por
  ejemplo, un documento de cliente con columnas en otro orden, o con una columna extra
  antes de "Item"), la función no encuentra las columnas correctas y no distribuye marca
  alguna, o distribuye a la columna equivocada, sin ninguna validación ni error — el
  guard de entrada solo verifica que exista **alguna** fila con más columnas que
  `PRICE_COL` (`parsers.py:284-285`), no que el layout sea el esperado.
- **Prioridad**: Media.
- **Archivo**: `parsers.py:262-348` (`_distribute_brands`).
- **Observaciones**: [IMPLEMENTADO] el acoplamiento a un layout hardcodeado, confirmado
  leyendo la función completa. Los 6 tests de `tests/test_brand_distribution.py` (clase
  `TestDistributeBrands`) todos usan el mismo layout de 7 columnas
  (`_row(proveedor, item, cant, desc, unidad, pu, importe)`, comentario en
  `test_brand_distribution.py:38`) — ningún test ejercita un layout distinto ni verifica
  qué pasa si el layout real difiere. Ver [`pendientes.md`](./pendientes.md) P1.
