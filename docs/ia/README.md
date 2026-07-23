# Componentes de IA (Gemini) — Drogueria Nueva Era

> Alcance: los componentes de inteligencia artificial (Google Gemini) del proyecto, hoy
> ubicados exclusivamente en el backend legacy `services/extraccion/`. Este documento es
> transversal a los módulos técnicos ya cubiertos en `docs/modulos/extraccion_ia/`,
> `docs/modulos/extraccion_api/` y `docs/modulos/extraccion_validacion/` — no los
> reemplaza, los sintetiza con foco específico en "qué hace la IA, cómo, y con qué
> riesgo". Toda afirmación fue releída contra el código fuente real en esta sesión
> (`robot.py`, `robot_comparativas.py`, `parsers.py`, `config.py`, `gemini_errors.py`,
> `main.py`, todos en `services/extraccion/`), no copiada ciegamente de la documentación
> previa de FASE 2.
>
> `services/presupuestacion/` **no** usa IA — confirmado por grep en esta sesión sobre
> todo `services/presupuestacion/` buscando `genai`, `generativeai`, `gemini` (case
> insensitive), sin resultados fuera de comentarios/nombres de tabla que referencian al
> otro backend. [IMPLEMENTADO].

## 1. Objetivo

La IA resuelve un único problema de negocio: **convertir documentos comerciales no
estructurados (PDF, Excel, imágenes, HTML) en datos tabulares estructurados**, sin
digitación manual, para dos casos de uso distintos:

- **Licitaciones/pedidos**: un documento de un solo proveedor → CSV de ítems
  (`item;cantidad;descripcion;origen`). Pipeline: `robot.py:procesar_archivo`.
- **Comparativas de precios**: un documento con precios de múltiples proveedores para
  los mismos ítems → CSV de ofertas por renglón/proveedor
  (`renglon;proveedor;marca;precio;cliente`, top-3 por renglón). Pipeline:
  `robot_comparativas.py:procesar_comparativa`.

Ambos pipelines son invocados exclusivamente desde `POST /procesar` en
`services/extraccion/main.py` [IMPLEMENTADO] (`main.py:26-30` importa ambas funciones;
`docs/modulos/extraccion_ia/casos_de_uso.md` confirma que es el único consumidor en todo
el repo, verificado en esta sesión con el mismo grep negativo sobre
`services/presupuestacion/`).

Adicionalmente, Gemini se usa como **parser de último recurso** dentro del pipeline de
parseo de documentos (`parsers.py:_parse_image`, Gemini Vision) — no como generador de
datos de negocio en sí, sino como OCR/extracción de texto cuando no hay forma más barata
de leer el documento (PDF escaneado, imagen suelta). Ver §3-4.

## 2. Modelo

| Constante | Valor | Archivo:línea |
|---|---|---|
| `PRIMARY_MODEL` | `gemini-2.5-flash` | `config.py:76` |
| `FALLBACK_MODEL` | `gemini-3-flash-preview` | `config.py:77` |
| `MODEL_NAME` | `= PRIMARY_MODEL` (alias, sin consumidores confirmados en el repo) | `config.py:78` |

**[IMPLEMENTADO]** `generate_with_fallback(client, contents, config=None)`
(`config.py:96-105`) intenta siempre `PRIMARY_MODEL` primero; ante **cualquier**
excepción (`except Exception as exc`, `config.py:102`, sin filtrar por tipo) reintenta
una vez con `FALLBACK_MODEL`, reutilizando el mismo `client` (misma API key). No hay
lógica que vuelva a intentar el modelo primario después.

**Configuración de generación**:

- No se fija `temperature` en ningún punto del código — confirmado por grep sobre los 5
  archivos de IA en esta sesión, sin resultados para `temperature`. Se usa el default
  del SDK `google-genai` para ambos modelos. [IMPLEMENTADO] (ausencia verificada).
- `robot.py:procesar_archivo` (licitaciones/pedidos) llama a `generate_with_fallback`
  **sin** pasar `config` (`robot.py:333`, `:335`) — usa el límite de `max_output_tokens`
  por default del SDK, no hay override explícito.
- `robot_comparativas.py:_llamar_gemini_json` sí pasa `config=_JSON_CONFIG`
  (`robot_comparativas.py:136`), con:
  ```python
  _JSON_CONFIG = types.GenerateContentConfig(
      response_mime_type="application/json",
      max_output_tokens=65_536,   # gemini-2.5-flash max; prevents mid-JSON truncation
  )
  ```
  (`robot_comparativas.py:47-50`) — este es el único punto del código donde se pide
  *structured output* (JSON forzado por `response_mime_type`) en vez de texto libre.
- `parsers.py:_parse_image` (Vision) llama a `generate_with_fallback` sin `config`
  (`parsers.py:662`) — mismo default de SDK que `robot.py`.

**Cliente y API keys**: se usa el SDK **`google-genai`** (`from google import genai`,
`config.py:8`), no el paquete legacy `google-generativeai` — confirmado en
`requirements.txt:17` (`google-genai`, sin pin de versión explícito, a diferencia de
casi todas las demás dependencias del archivo que sí están fijadas con `==`). Esto
corrige una imprecisión de nomenclatura: `docs/modulos/extraccion_ia/README.md:1`
titula el módulo citando el paquete `google.generativeai`, pero el import real es
`from google import genai` del paquete `google-genai` (SDK nuevo unificado de Google, no
el SDK legacy `google-generativeai`). [IMPLEMENTADO], ver §12.

`GEMINI_API_KEYS` (coma-separado, con fallback a `GEMINI_API_KEY` singular si la
primera no está definida, `config.py:61-67`) crea un `genai.Client` por key
(`CLIENTS = [genai.Client(api_key=key) for key in api_keys]`, `config.py:80`).
`get_next_client()` rota entre ellos con un `threading.Lock` (`config.py:89-94`) —
round-robin thread-safe para distribuir carga entre cuotas de distintas API keys.

## 3. Entrada

| Caso | Cómo se le pasa el contenido a Gemini | Evidencia |
|---|---|---|
| Documento genérico (no-Excel), licitación/pedido | `client.files.upload(file=str(ruta_archivo))` (File API de Gemini) + prompt de texto, pasados como lista `[prompt, archivo_subido]` | `robot.py:298`, `:335` |
| Excel, licitación/pedido | El Excel se lee con pandas, se normaliza (`_normalizar_excel`) y se serializa a CSV `;`-separado **inline en el prompt** (texto plano, sin upload) | `robot.py:293-295`, `:332` |
| Comparativas | El documento ya fue convertido a Markdown por `parsers.py:parse_document` (ver §6) **antes** de llegar a Gemini — nunca se sube el archivo binario original para comparativas, se envía el Markdown comprimido como texto en el prompt | `robot_comparativas.py:136` (`f"{prompt}\n\n{markdown}"`) |
| Vision (PDF escaneado / imagen, dentro de `parsers.py`) | `CLIENT.files.upload(file=str(filepath))` + `_VISION_PROMPT` como texto, lista `[_VISION_PROMPT, uploaded_file]` | `parsers.py:661-662` |

**[IMPLEMENTADO]**: para comparativas, Gemini **nunca** recibe el PDF/Excel/imagen
original directamente — siempre recibe Markdown ya extraído por el pipeline de parseo
(pdfplumber/Docling/Vision, ver §6). Para licitaciones/pedidos no-Excel, en cambio,
Gemini sí recibe el archivo original completo vía File API (`robot.py:298`), sin pasar
por `parsers.py`.

## 4. Salida

### Licitaciones/pedidos (`robot.py`)

Texto libre, se le pide a Gemini que devuelva **CSV** (no structured output real — no
hay `response_mime_type` ni schema forzado). Validación mínima post-respuesta:

- Se remueven fences ```` ```csv ```` / ```` ``` ```` y se agrega salto de línea final si
  falta (`robot.py:338-340`).
- Se exige que `"item;"` aparezca en minúsculas en el texto; si no, `ValueError("Respuesta
  invalida (no es CSV)")` (`robot.py:341-342`). **No hay validación de esquema más
  estricta** (número de columnas, tipos, filas bien formadas) antes de escribir el
  archivo — [IMPLEMENTADO], confirmado leyendo la función completa.

### Comparativas (`robot_comparativas.py`)

**Sí hay structured output real**: `response_mime_type="application/json"` fuerza a
Gemini a devolver JSON válido sintácticamente (`_JSON_CONFIG`, `robot_comparativas.py:
47-50`). El JSON esperado (no es un JSON Schema formal pasado al SDK, es un ejemplo en
el prompt — ver §5) tiene la forma:

```json
{
  "proveedores": ["Provider A", "Provider B"],
  "renglones": [
    {
      "renglon": 1,
      "proveedores_precios": {
        "Provider A": {"precio": "12.50", "marca": "ELEA"},
        "Provider B": {"precio": "13.00", "marca": "sin marca"}
      }
    }
  ]
}
```

Parseo en `_llamar_gemini_json` (`robot_comparativas.py:122-169`):

1. Revisa `finish_reason` del primer candidato **antes** de parsear; si contiene
   `"MAX_TOKENS"`, levanta `GeminiTruncationError` sin intentar `json.loads`
   (`robot_comparativas.py:147-150`).
2. `json.loads(response.text)`; si falla, también `GeminiTruncationError`
   (`robot_comparativas.py:152-158`) — el mismo tipo de error cubre truncamiento
   detectado por `finish_reason` y JSON sintácticamente inválido por cualquier otra
   causa.
3. Si el resultado es una `list` en vez de `dict` (Gemini a veces no respeta la
   estructura pedida), se infiere estructura por la presencia de la clave `"renglon"`
   en el primer elemento, o se devuelve vacío (`robot_comparativas.py:160-167`).

El JSON de cada chunk se combina con los demás (dedupe de proveedores, concat de
renglones) y pasa por el filtro `_filtrar_top_3_por_renglon` (Python puro, sin Gemini,
`robot_comparativas.py:732-823`) antes de escribirse como CSV final
(`renglon;proveedor;marca;precio;cliente`, `_escribir_csv`, `:831-863`).

### Vision (`parsers.py:_parse_image`)

Texto libre en Markdown (tablas preservadas como tablas Markdown, según el prompt —
ver §5), sin ninguna validación de formato post-respuesta más allá de
`response.text.strip()` (`parsers.py:663`). El texto resultante se trata como cualquier
otro Markdown parseado y sigue el flujo normal de `parse_document` — no hay verificación
de que el contenido extraído sea coherente.

## 5. Prompts

Hay **3 prompts hardcodeados** en el código (ninguno se genera dinámicamente por IA, ni
hay templates externos/configurables por archivo de config — todos son f-strings o
strings literales en el código Python):

### 5.1 Licitación/pedido — `robot.py:312-326`

```
Analiza este {tipo_doc} y extrae la informacion solicitada en formato CSV.
{estructura}
CAMPOS:
item;cantidad;descripcion;origen

REGLAS:
- Devuelve SOLO CSV
- Usa punto y coma (;)
- Incluye encabezado
- Una fila por producto
- Sin texto adicional
- No uses comillas
- El campo origen debe ser exactamente: {cliente}
```

`{tipo_doc}` es `"EXCEL"` o `"DOCUMENTO"` según la extensión (`robot.py:301`).
`{estructura}` se antepone solo para Excel, con una nota de que hay una cabecera a
ignorar y una tabla a extraer (`robot.py:304-308`). `{cliente}` se deriva del nombre de
archivo (primer segmento antes de `_`, `obtener_cliente`, `robot.py:20-21`). Si el
caller pasa `instrucciones_extra` (instrucciones específicas por cliente, §8 de
`docs/modulos/extraccion_ia/reglas.md`), se agregan al final del prompt
(`robot.py:328-329`).

### 5.2 Comparativas — `_PROMPT_UNIFIED`, `robot_comparativas.py:64-98`

Prompt completo, en inglés (a diferencia del prompt de `robot.py`, en español):

```
Extract data from this price comparison document (comparativa de precios).

These documents list items/products and compare prices from multiple providers/suppliers.
Structure varies across documents but always contains:
- Items with a number (renglon/item), description, and quantity
- For each item: providers with their quoted unit price and brand (marca)
- Providers that did not quote show "NO COTIZA", "No cotiza", empty cells, or similar
- Each provider offers their OWN brand — different providers supply different brands for the same item

TABLE STRUCTURE NOTE — brands in Description column:
Each provider row may have its brand in the Descripción/Description column of that same row.
The brand is the commercial name of the product (e.g. "ELEA", "KLONAL", "LAFEDAR").
Catalog codes like "PM59408" or "C.48432" are internal identifiers — do NOT include them in marca.
If a row has no brand in its Description column, use "sin marca".

Return ONLY valid JSON:
{
  "proveedores": ["Provider A", "Provider B"],
  "renglones": [
    {
      "renglon": 1,
      "proveedores_precios": {
        "Provider A": {"precio": "12.50", "marca": "ELEA"},
        "Provider B": {"precio": "13.00", "marca": "sin marca"}
      }
    }
  ]
}

RULES:
- "marca": brand name only, no catalog codes (PM/C. numbers). Use "sin marca" if no brand is found
- "precio": unit price as a number string, empty string if provider does not quote
- "proveedor": full provider name. Use "sin proveedor" if name cannot be determined
- Include ALL providers for every renglon, even those that don't quote
- Return ALL items found
```

Es el mismo prompt para los dos flujos de chunking (Markdown y páginas de PDF, ver §6);
si el caller pasa `instrucciones_extra`, se concatenan (`robot_comparativas.py:948-952`).
No hay prompts distintos por tipo de proveedor o formato de documento — un único prompt
para toda comparativa, independiente de su origen.

### 5.3 Vision (extracción de texto genérica) — `_VISION_PROMPT`, `parsers.py:61-65`

```
Extract all text from this document. Preserve table structure as Markdown tables. Return only the extracted text with no additional commentary.
```

El comentario del código lo marca explícitamente como "exact text per spec"
(`parsers.py:59`). Es el prompt más simple de los 3 — no pide ningún formato de salida
estructurado, solo texto/Markdown fiel al documento.

## 6. Flujo técnico

### 6.1 Licitaciones/pedidos (`robot.py:procesar_archivo`, `:267-359`)

```
archivo subido por usuario (vía POST /procesar en main.py, fuera de este árbol)
  │
  ├─ Excel (.xls/.xlsx) ──► pandas.read_excel ──► _normalizar_excel (fuzzy match
  │                          de columnas) ──► CSV inline en el prompt
  │
  └─ Documento genérico ──► client.files.upload() (File API de Gemini)
  │
  ▼
generate_with_fallback(client, prompt [+ archivo]) ──► respuesta CSV en texto libre
  │
  ▼
limpieza: strip fences, validar "item;", _limpiar_cantidad, _rellenar_items_incrementales
  │
  ▼
escribir CSV en OUTPUT_BASE/{cliente}/ + mover original a Procesados/
  │
  ▼
Path del CSV devuelto al caller (main.py) — la persistencia en Supabase ocurre
DESPUÉS de este pipeline, fuera de estos 5 archivos (ver §9 y base_de_datos.md
de extraccion_ia)
```

Toda la función está envuelta por `@handle_gemini_errors(max_retries=4,
backoff_factor=40.0)` (`robot.py:267`) — si algo falla dentro (incluyendo el upload),
se reintenta la función **completa** desde el principio (nuevo cliente, nuevo upload).

### 6.2 Comparativas (`robot_comparativas.py:procesar_comparativa`, `:893-1007`)

```
archivo subido
  │
  ├─ .pdf con > 20 páginas (_PDF_PAGE_THRESHOLD) ──► Rama A: chunking por páginas
  │    _split_pdf_by_pages (15 páginas/chunk, 1 de overlap, pypdf)
  │      │
  │      ▼ (ThreadPoolExecutor, hasta 3 workers en paralelo)
  │    por chunk: parse_document(chunk) [pdfplumber/Docling/Vision, ver 6.3]
  │      → _comprimir_markdown → _llamar_gemini_json(_PROMPT_UNIFIED, markdown)
  │
  └─ resto (no-PDF, o PDF chico) ──► Rama B: chunking por Markdown
       parse_document(archivo completo) → _comprimir_markdown
         │
         ├─ Markdown ≤ 40.000 chars ──► un único _llamar_gemini_json
         └─ Markdown > 40.000 chars ──► _split_markdown_chunks (15 ítems/chunk)
              │ (mismo ThreadPoolExecutor, 3 workers)
              ▼
            por chunk: _llamar_gemini_json
              │
              └─ si GeminiTruncationError ──► _split_chunk_in_half ──► 2 llamadas
                 independientes (sin reintento adicional si vuelve a truncarse)
  │
  ▼
combinar resultados de todos los chunks (dedupe proveedores, concat renglones);
best-effort guardar_chunk() en Supabase si hay session_id (try/except, solo logea)
  │
  ▼
_filtrar_top_3_por_renglon (Python puro, sin Gemini) ──► top 3 precios por renglón
  │
  ▼
_escribir_csv + _mover_a_procesados
  │
  ▼
Path del CSV devuelto al caller
```

Cada `_llamar_gemini_json` individual está decorada con `@handle_gemini_errors
(max_retries=4, backoff_factor=40.0)` (`robot_comparativas.py:122`) — el reintento con
backoff es **por chunk**, no para el pipeline completo (a diferencia de licitaciones).

### 6.3 Parseo de documentos previo a Gemini (`parsers.py:parse_document`)

Router por extensión (`_EXTENSION_ROUTER`, `parsers.py:699-711`, 10 extensiones → 5
handlers: `_parse_excel`, `_parse_ods`, `_parse_pdf`, `_parse_html`, `_parse_image`).
Para PDF, cadena de fallback documentada en detalle en
`docs/modulos/extraccion_ia/arquitectura.md`: **pdfplumber nativo (sin IA) → Docling
lightweight (ML local, sin IA) → Gemini Vision (única rama que llama a la API paga)**,
como último recurso cuando Docling no está instalado o falla, o cuando el PDF es
detectado como escaneado. Este es el único punto donde Gemini participa del *parseo*
(no de la extracción de datos de negocio) — la llamada real está en `_parse_image`
(`parsers.py:624-692`, ver §3-4).

### 6.4 Persistencia — fuera de estos 5 archivos

**[IMPLEMENTADO]**: ninguno de los 5 archivos de IA importa `supabase_client`
(confirmado por grep en `docs/modulos/extraccion_ia/base_de_datos.md`, releído en esta
sesión y consistente con lo verificado acá). El resultado de ambos pipelines es
siempre un `Path` a un CSV en el filesystem local (`OUTPUT_BASE`/
`COMPARATIVAS_OUTPUT_BASE`, `config.py:111-112`). La persistencia real ocurre en
`main.py` (`schedule_persist_output`, fuera del alcance de este documento) y, para el
caso de negocio final, en el módulo `extraccion_validacion` de
`services/presupuestacion/`, vía `POST /extracciones/{id}/validar` — ver §9.

La única excepción parcial: `guardar_chunk()` (best-effort, envuelto en `try/except`
que solo logea `warning`, nunca interrumpe el pipeline) desde
`robot_comparativas.py:556-560` y `:713-717`, cuando el caller pasa `session_id` — pero
esto persiste el **chunk crudo procesado**, no el resultado de negocio validado.

## 7. Nivel de confianza

**No existe ningún score de confianza calculado ni expuesto sobre lo extraído por
Gemini.** [IMPLEMENTADO] (ausencia verificada): grep sobre los 5 archivos de IA en esta
sesión buscando `confianza`, `confidence`, `score` (case insensitive) solo encuentra
matches de `score`/`mejor_score` dentro de `_mejor_match_columna`,
`_score_cantidad`/`_score_descripcion` (`robot.py:49-104`, `:218-237`) — que son
**scores de similitud de texto para el fuzzy matching de columnas Excel**
(RN-EXTRACCIONIA-009, comparación de nombres de columna contra sinónimos), no un score
de confianza sobre la calidad de la extracción de Gemini en sí. No hay ningún campo
`confianza`/`confidence` en el CSV de salida de ninguno de los dos pipelines
(`item;cantidad;descripcion;origen` para licitaciones, `renglon;proveedor;marca;precio;
cliente` para comparativas — ninguna de las dos tiene una columna de ese tipo,
confirmado en `robot.py:341` y `robot_comparativas.py:831-863`).

La única señal indirecta de "algo salió mal" que el sistema sí produce es
`finish_reason` (truncamiento) y la validación superficial de formato (`"item;"` en
licitaciones, JSON parseable en comparativas) — ninguna mide calidad semántica de la
extracción (marca correcta, precio correcto, ítem bien identificado).

## 8. Qué automatiza

Reemplaza la digitación manual de:

- **Licitaciones/pedidos de proveedor**: pasar un PDF/Excel/imagen con una lista de
  productos a filas de `item;cantidad;descripcion;origen`, incluyendo la identificación
  del proveedor por convención de nombre de archivo (`obtener_cliente`).
- **Comparativas de precios multi-proveedor**: cruzar precios y marcas de varios
  proveedores por ítem/renglón desde un documento (a menudo un PDF con tablas complejas
  de múltiples páginas), incluyendo el ranking de las 3 ofertas más baratas por renglón
  (`_filtrar_top_3_por_renglon`) — esto último es lógica de negocio Python pura, no
  generada por Gemini, pero opera sobre datos que sí extrajo Gemini.
- **OCR de documentos escaneados/imágenes** que de otro modo requerirían transcripción
  manual, vía la rama Vision del parser de PDF.

## 9. Qué requiere intervención humana

**[IMPLEMENTADO]**, con evidencia cruzada de `docs/modulos/extraccion_validacion/`
(releído en esta sesión): el resultado de estos pipelines (el CSV) **no se materializa
automáticamente en las tablas de negocio de `presupuestacion/`**. Existe un paso de
validación humana obligatorio, expuesto como `POST /extracciones/{extraction_id}
/validar` en `services/presupuestacion/extraccion/router.py` — un módulo
**completamente distinto** del pipeline de IA (vive en el otro backend), que:

1. Lee la fila de `extraction_results` (producida por `services/extraccion/main.py`
   tras correr el pipeline de IA) y su `csv_disk_path`.
2. Rechaza si ya fue `validado` (`ConflictError`, RN-EXTRACCIONVALIDACION-003).
3. Materializa las filas del CSV en `items_proceso` (licitación/cotización, disparando
   matching automático por cada ítem, `matching.service.procesar_matching_item`) o en
   `comparativas` + `ofertas_items` (comparativa, con versionado si ya había una
   comparativa vigente para el mismo proceso comercial).
4. Marca `extraction_results.validado = TRUE`.

Este endpoint es, hoy, el único punto de intervención humana formal sobre el resultado
de la IA — pero **no hay ningún dato en el código que indique que un humano revisa el
contenido de cada fila antes de confirmarlo**: `validar_extraccion` no recibe en su
payload ninguna versión editada del CSV, solo el `extraction_id`
(`ValidarExtraccionRequest`, `docs/modulos/extraccion_validacion/api.md`, releído en
esta sesión) — es decir, el endpoint **materializa el CSV tal cual lo generó Gemini**,
sin mecanismo de edición de filas individuales expuesto en esta capa. "Si existe una
pantalla de edición de filas antes de confirmar: pendiente de definición funcional" —
no se encontró ningún componente de frontend que lo implemente.

**Hallazgo relevante — no hay pantalla de frontend funcional para este paso todavía.**
Releyendo `docs/modulos/frontend_carga_documentos/README.md` en esta sesión: la
pantalla "Validar extracción" (que debería consumir este endpoint) está en
`openspec/changes/validar-extraccion/`, con `proposal.md:3` diciendo explícitamente
"Estado: sin empezar" — **sin `spec.md` ni `tasks.md`**, es decir, sin código de
frontend real. El componente más cercano que existe hoy (`NuevaLiciCotiDialog.tsx`) es
para *crear* un proceso comercial, no para revisar/editar una extracción, y además está
huérfano (sin ningún caller en el árbol de rutas del frontend). **Conclusión: hoy, la
única forma de invocar `POST /extracciones/{id}/validar` es directamente contra la API**
— no hay UI de validación humana operativa en el MVP actual. [IMPLEMENTADO], verificado
cruzando ambos módulos ya documentados en `docs/modulos/`.

## 10. Manejo de errores

### 10.1 Clasificación y reintento — `gemini_errors.py:handle_gemini_errors`

`_classify_gemini_error(e)` (`gemini_errors.py:55-66`) clasifica por palabras clave en
`str(e).lower()`, **no por tipo de excepción**:

| Orden | Keywords | Clase resultante |
|---|---|---|
| 1 | `quota`, `exhausted`, `resource_exhausted`, `out of quota` | `GeminiQuotaExceededError` |
| 2 | `rate limit`, `too many requests`, `429`, `deadline exceeded`, `503`, `high demand`, `unavailable` | `GeminiRateLimitError` |
| 3 (default) | cualquier otra | `GeminiAPIError` |

Política de reintento (`gemini_errors.py:81-131`), envuelta en un `for attempt in
range(max_retries)`:

- `GeminiTruncationError` (truncamiento por `MAX_TOKENS` o JSON inválido, ver §4): **no
  se reintenta**, se relanza de inmediato (`gemini_errors.py:84-85`, comentario
  explícito "deterministic — retrying same input is pointless").
- `GeminiQuotaExceededError`: **no se reintenta**, se relanza de inmediato
  (`gemini_errors.py:100-102`) — se asume permanente hasta reseteo de cuota.
- `GeminiRateLimitError`: backoff exponencial `wait = (2 ** attempt) * backoff_factor`
  segundos (`gemini_errors.py:104-117`).
- Cualquier otro (`GeminiAPIError`): backoff lineal corto `wait = 1.0 * (attempt + 1)`
  segundos (`gemini_errors.py:119-131`).

Aplicado con `max_retries=4, backoff_factor=40.0` en ambos pipelines
(`robot.py:267`, `robot_comparativas.py:122`) — muy por encima de los defaults del
decorador (`max_retries=3, backoff_factor=2.0`, `gemini_errors.py:69`). Con esos
valores, un error de rate-limit persistente espera `40s, 80s, 160s` en los intentos
1-3 antes de fallar en el intento 4 (~280s de espera acumulada en el peor caso).

### 10.2 Fallback de modelo — `config.py:generate_with_fallback`

Capa **separada** de la anterior: ante cualquier excepción del modelo primario,
reintenta una vez con el modelo fallback (`config.py:96-105`, `except Exception as
exc` genérico). Esto significa que, en el peor caso, una sola llamada de negocio puede
disparar hasta **8 llamadas de red** (2 modelos × 4 reintentos con backoff) sin que
ningún comentario del código documente ese número — este dato ya estaba señalado como
P2(1) en `docs/modulos/extraccion_ia/pendientes.md`, confirmado de nuevo en esta
sesión leyendo ambos archivos juntos.

### 10.3 Mapeo a HTTP en `main.py` (fuera del árbol de IA, pero consumidor directo)

```
UnsupportedFormatError    -> 415  (main.py:283-288)
ParserError                -> 422  (main.py:291-296)
NoProvidersDetectedError   -> 422  (main.py:299-304)
GeminiQuotaExceededError   -> 503  (main.py:307-312)
GeminiRateLimitError       -> 429  (main.py:315-320)
GeminiAPIError              -> 500  (main.py:323-328)
Exception genérica          -> 500  (main.py:336)
```

[IMPLEMENTADO], verificado línea por línea en `main.py`. `_GEMINI_SEMAPHORE =
asyncio.Semaphore(15)` (`main.py:67`) limita a 15 el número de invocaciones
concurrentes del pipeline de IA por instancia de proceso — no es manejo de error, pero
es el único mecanismo de control de carga hacia Gemini presente en el código.

### 10.4 Vision (`parsers.py:_parse_image`)

Reintenta una vez ante cualquier excepción (2 intentos totales, `parsers.py:653`), con
un `finally` que **siempre** intenta borrar el archivo subido a Gemini
(`CLIENT.files.delete`, `parsers.py:678-690`), incluso si la extracción falló en ambos
intentos — el error de borrado en sí también se atrapa y solo se logea
(`parsers.py:685-690`), nunca enmascara la excepción original de extracción.

## 11. Riesgos

Solo riesgos con evidencia directa en el código, releídos en esta sesión (no
especulación):

1. **[IMPLEMENTADO] Ausencia total de score de confianza.** Ver §7. El sistema no tiene
   ninguna señal cuantitativa de "qué tan seguro está Gemini" de una fila extraída;
   combinado con el hallazgo de §9 (no hay UI de edición fila-por-fila antes de
   confirmar), el flujo actual asume que el CSV generado por Gemini es correcto salvo
   que el humano rechace la extracción completa o la corrija fuera del sistema antes de
   subir el archivo original de nuevo.

2. **[IMPLEMENTADO] `generate_with_fallback` no distingue tipos de error — una API key
   inválida dispara el mismo camino que un 503 transitorio.** `config.py:100-105`, ya
   documentado como P1(2) en `docs/modulos/extraccion_ia/pendientes.md`, confirmado de
   nuevo en esta sesión: si la key rota por `get_next_client()` está revocada, la
   primera llamada falla, se reintenta con el modelo fallback usando el **mismo
   cliente** (misma key rota), también falla, y el mensaje final que ve el caller es
   sobre el modelo fallback — oculta la causa raíz real (key inválida).

3. **[IMPLEMENTADO — hallazgo nuevo de esta sesión] `_parse_image` (Vision) siempre usa
   el mismo cliente (`CLIENT`, primera API key), sin round-robin, a diferencia de
   `robot.py` y `robot_comparativas.py`.** `parsers.py:28` importa `CLIENT` (no
   `get_next_client`) de `config.py`; `_parse_image` lo usa directamente en
   `parsers.py:661-662`, `:681`. Los otros dos pipelines llaman a `get_next_client()`
   antes de cada llamada a Gemini para distribuir carga entre keys
   (`robot.py:289`, `robot_comparativas.py:135`). Esto significa que **todo el tráfico
   de Vision (PDFs escaneados + imágenes sueltas) se concentra en una sola API key**,
   independientemente de cuántas keys estén configuradas en `GEMINI_API_KEYS` — un
   volumen alto de documentos escaneados podría agotar la cuota de esa key específica
   mientras las demás quedan sin uso por esa vía. No se encontró ningún comentario que
   indique que esto sea intencional. `docs/modulos/extraccion_ia/pendientes.md` P2(2)
   solo señala que `CLIENT` es un import muerto en `robot.py`/`robot_comparativas.py` —
   no señala este uso real (y asimétrico) en `parsers.py`. Se documenta acá como
   hallazgo nuevo.

4. **[IMPLEMENTADO] `_distribute_brands` (usado dentro de la rama pdfplumber del parseo
   de PDF) asume un layout de columnas fijo sin validarlo**, lo que puede producir
   marcas asignadas a la columna equivocada de forma silenciosa si un cliente sube una
   comparativa con estructura de tabla distinta (`parsers.py:262-348`,
   RN-EXTRACCIONIA-015 en `docs/modulos/extraccion_ia/reglas.md`, ya releído y
   confirmado). No es un riesgo de la llamada a Gemini en sí, pero contamina el
   Markdown que **sí** se envía a Gemini como entrada para comparativas — un error acá
   se propaga directamente al prompt.

5. **[IMPLEMENTADO] `robot.py` (licitaciones/pedidos) no tiene ningún mecanismo de
   chunking ni de recuperación ante truncamiento**, a diferencia de
   `robot_comparativas.py`. Si un pedido/licitación individual excede el límite de
   salida del modelo, la única validación es que la respuesta contenga `"item;"` — no
   detecta un CSV cortado a mitad de fila (D-EXTRACCIONIA-006 en
   `docs/modulos/extraccion_ia/decisiones.md`, confirmado en esta sesión que
   `robot.py:333`/`:335` no pasa ningún `config` con `max_output_tokens`).

6. **[IMPLEMENTADO] Gran parte del pipeline de parseo de PDF (incluyendo la decisión de
   cuándo cae a Gemini Vision) no tiene test directo.** `_parse_pdf`, `is_scanned_pdf`,
   `_extract_native_pdf` y el propio `_parse_image` no aparecen en ningún `import`/
   `patch(...)` de `tests/` (confirmado por grep en esta sesión sobre `tests/`, sin
   resultados para esos nombres) — un cambio que rompa la decisión de fallback a Vision
   (por ejemplo, que empiece a llamar a Gemini Vision para PDFs nativos por error) no
   sería detectado por la suite actual.

## 12. Dependencias

- **Librería**: `google-genai` (SDK nuevo unificado de Google; import real
  `from google import genai`, `config.py:8`), **sin versión pineada** en
  `requirements.txt:17` — a diferencia de casi todas las demás dependencias del mismo
  archivo, que sí fijan versión exacta con `==`. [IMPLEMENTADO]. Dependencias asociadas
  también presentes: `google-ai-generativelanguage==0.6.15`,
  `google-api-core==2.25.2`, `google-api-python-client==2.188.0` (`requirements.txt:
  12-14`) — no se pudo confirmar en esta sesión si estas tres son consumidas
  directamente por algún archivo de IA o son dependencias transitivas de `google-genai`
  (fuera del alcance verificable sin inspeccionar el árbol de dependencias instalado).
- **Variables de entorno**:
  - `GEMINI_API_KEYS` (coma-separado, preferida) o `GEMINI_API_KEY` (singular,
    fallback) — `config.py:61-67`. Si ninguna está definida, `RuntimeError` al importar
    el módulo (falla de arranque, no en runtime de una request).
  - `OUTPUT_BASE_DIR` (o `config_local.py`) — no es una variable de IA en sí, pero
    condiciona dónde se escriben los CSV resultado del pipeline (`config.py:40-58`).
- **Endpoints internos que consumen la IA**: único punto confirmado,
  `POST /procesar` en `services/extraccion/main.py` (`main.py:26-30` importa las
  funciones; el endpoint las invoca dentro de `asyncio.to_thread` + el semáforo de
  concurrencia de §10.3). Ningún endpoint de `services/presupuestacion/` invoca
  directamente estas funciones — el único acoplamiento es indirecto, vía el CSV en
  disco y la fila de `extraction_results` que `POST /extracciones/{id}/validar`
  consume (ver §9).

## Fuentes releídas en esta sesión

Código: `services/extraccion/{robot.py, robot_comparativas.py, parsers.py, config.py,
gemini_errors.py, main.py}`, `requirements.txt`.

Documentación previa releída como insumo (no copiada sin verificar): todo
`docs/modulos/extraccion_ia/` (README, arquitectura, flujo, reglas, api, casos_de_uso,
decisiones, pendientes, base_de_datos), `docs/modulos/extraccion_validacion/{README,
flujo}.md`, `docs/modulos/frontend_carga_documentos/README.md`.
