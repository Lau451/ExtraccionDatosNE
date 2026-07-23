# Flujos — Extracción IA (legacy)

Los 3 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en esta
sesión.

## Flujo 1 — Extracción de licitación/pedido (`robot.py:procesar_archivo`)

1. El caller (fuera de este módulo, ver [`casos_de_uso.md`](./casos_de_uso.md)) invoca
   `procesar_archivo(ruta_archivo, nombre_original, session_id=..., instrucciones_extra=...)`,
   envuelto por el decorador `@handle_gemini_errors(max_retries=4, backoff_factor=40.0)`
   (`robot.py:267`).
2. Se deriva `nombre_base`, `extension_original` y `cliente` del nombre de archivo
   (`obtener_cliente`: primer segmento antes de `_`, `robot.py:20-21`, `:275-283`).
3. `get_next_client()` obtiene el próximo cliente Gemini en round-robin
   (`robot.py:289`, ver [`decisiones.md`](./decisiones.md) D-EXTRACCIONIA-005) — este
   mismo cliente se reutiliza para upload y para la llamada a Gemini, sin volver a
   pedir uno nuevo dentro de la misma ejecución (confirmado por
   `tests/test_key_fix.py:test_mismo_cliente_para_upload_y_generate`, fuera del
   alcance de los 5 archivos de este módulo pero relevante como evidencia).
4. **Rama Excel** (`.xls`/`.xlsx`): se lee con pandas (`engine="xlrd"` o `"openpyxl"`),
   se normaliza con `_normalizar_excel` (RN-EXTRACCIONIA-009) y se serializa a CSV
   (`;`-separado) para incluirlo en el prompt como texto (`robot.py:291-295`, `:332`).
5. **Rama documento genérico** (no-Excel): se sube el archivo a Gemini con
   `client.files.upload()` (`robot.py:297-299`) y se referencia en la llamada.
6. Se arma el prompt (RN-EXTRACCIONIA-001), agregando `instrucciones_extra` si el
   caller las pasó (§8, formato por cliente, `robot.py:328-329`).
7. `generate_with_fallback(client, prompt_o_lista, config=None)` llama a Gemini —
   internamente puede reintentar una vez con el modelo fallback ante cualquier
   excepción (`config.py:96-105`, RN-EXTRACCIONIA-007).
8. Se limpia la respuesta: se remueven fences ```` ```csv ````/```` ``` ````, se agrega
   salto de línea final si falta, y se valida que contenga `"item;"` en minúsculas — si
   no, `ValueError("Respuesta invalida (no es CSV)")` (`robot.py:336-342`).
9. Se aplican las dos heurísticas de limpieza post-Gemini, en este orden:
   `_limpiar_cantidad` (RN-EXTRACCIONIA-010) y luego `_rellenar_items_incrementales`
   (rellena la columna `item` si viene vacía, `robot.py:143-187`, `:344-345`).
10. Se escribe el CSV en `get_output_dir(origen_id=cliente)` con nombre único
    (`nombre_unico`, evita colisiones con `os.O_CREAT | os.O_EXCL`, `robot.py:24-35`) y
    se mueve el archivo original a `get_processed_dir(origen_id=cliente)`
    (`robot.py:347-357`).
11. Se devuelve el `Path` al CSV generado (`robot.py:359`).

Si en cualquier punto de los pasos 3-10 se levanta una excepción clasificable por
`gemini_errors.py` (RN-EXTRACCIONIA-008), el decorador del paso 1 reintenta la función
**completa** desde el paso 2 (nuevo `get_next_client()`, nuevo upload si aplica) hasta
`max_retries=4` veces, con el backoff correspondiente al tipo de error.

## Flujo 2 — Extracción de comparativas (`robot_comparativas.py:procesar_comparativa`)

1. El caller invoca `procesar_comparativa(ruta_archivo, nombre_original, session_id=...,
   instrucciones_extra=...)` (`robot_comparativas.py:893-899`; esta función pública **no**
   está decorada con `handle_gemini_errors` — el reintento con backoff ocurre a nivel de
   `_llamar_gemini_json`, más abajo en la pila, no a nivel de todo el pipeline).
2. Se deriva `nombre_base`, `extension` y `cliente` (mismas funciones que en Flujo 1,
   importadas de `robot.py`, `robot_comparativas.py:933-940`).
3. Se arma `prompt_efectivo` = `_PROMPT_UNIFIED` + `instrucciones_extra` si existen
   (`robot_comparativas.py:948-952`).
4. **Decisión de estrategia** (solo si la extensión es `.pdf`): se cuenta el número de
   páginas con `pypdf.PdfReader`; si supera `_PDF_PAGE_THRESHOLD=20`, se activa
   `usar_page_chunks=True` (RN-EXTRACCIONIA-004, `robot_comparativas.py:956-966`). Si
   falla el conteo, se degrada al flujo Markdown-completo con un warning.
5. **Rama A — PDF grande, chunking por páginas**
   (`_extraer_comparativa_por_paginas`, `robot_comparativas.py:650-729`):
   1. `_split_pdf_by_pages` genera N chunks de PDF temporales (15 páginas, 1 de
      overlap, vía `pypdf`).
   2. Cada chunk se procesa en un `ThreadPoolExecutor` de hasta
      `_MAX_PARALLEL_CHUNKS=3` workers, vía `_procesar_chunk_pdf`: parsea el chunk a
      Markdown con `parse_document` (import diferido, `robot_comparativas.py:642`),
      comprime el Markdown (`_comprimir_markdown`) y llama a `_llamar_gemini_json`.
   3. Cada chunk temporal se borra en el `finally` del loop de resultados
      (`robot_comparativas.py:696-700`), independientemente de éxito o fallo.
   4. Los resultados se combinan: proveedores deduplicados preservando primer orden de
      aparición, renglones concatenados. Si `session_id` fue provisto, cada resultado de
      chunk se persiste best-effort vía `guardar_chunk` (ver
      [`base_de_datos.md`](./base_de_datos.md)).
   5. Si no se detectó ningún proveedor en ningún chunk, se levanta
      `NoProvidersDetectedError`.
6. **Rama B — documento chico o no-PDF, chunking por Markdown**
   (`_extraer_comparativa`, `robot_comparativas.py:491-572`):
   1. `parse_document(ruta_archivo)` parsea el documento completo a Markdown (import
      diferido, `robot_comparativas.py:931`) — ver Flujo 3 para PDF.
   2. Se guarda una copia del Markdown crudo en `data/Salida/docling_output/{cliente}/`
      vía `_guardar_docling_output` (trazabilidad, no es persistencia de negocio,
      `robot_comparativas.py:978`).
   3. Se comprime el Markdown (`_comprimir_markdown`).
   4. Si `len(markdown) > _CHUNK_THRESHOLD` (RN-EXTRACCIONIA-003), se divide en chunks
      de ítems completos con `_split_markdown_chunks`; si no, se procesa como un único
      chunk.
   5. Cada chunk se procesa en paralelo (mismo `ThreadPoolExecutor` de hasta 3 workers)
      vía `_process_chunk`, que llama a `_llamar_gemini_json` y, ante
      `GeminiTruncationError`, aplica split-in-half automático
      (RN-EXTRACCIONIA-005/006).
   6. Se combinan resultados igual que en la Rama A (dedupe de proveedores, concat de
      renglones, persistencia best-effort de chunks).
   7. Si no se detectó ningún proveedor, `NoProvidersDetectedError`.
7. Si `all_data["renglones"]` viene vacío tras cualquiera de las dos ramas, se levanta
   `json.JSONDecodeError("No items could be extracted...")`
   (`robot_comparativas.py:984-989`).
8. `_filtrar_top_3_por_renglon` aplica el filtro de negocio (RN-EXTRACCIONIA-012),
   Python puro, sin llamada a Gemini.
9. Si no queda ninguna fila tras el filtro, `json.JSONDecodeError("No valid data after
   filtering...")` (`robot_comparativas.py:994-999`).
10. `_escribir_csv` escribe el CSV final (`renglon;proveedor;marca;precio;cliente`) en
    `COMPARATIVAS_OUTPUT_BASE/{cliente}/` con nombre único.
11. `_mover_a_procesados` mueve el archivo original a
    `COMPARATIVAS_OUTPUT_BASE/{cliente}/Procesados/`.
12. Se devuelve el `Path` al CSV generado.

Reintento a nivel de llamada individual: cada invocación a `_llamar_gemini_json` (dentro
de los pasos 5.ii/6.v) está decorada con `@handle_gemini_errors(max_retries=4,
backoff_factor=40.0)` (`robot_comparativas.py:122`) — el reintento con backoff ocurre
**por chunk**, no para el pipeline completo, a diferencia del Flujo 1.

## Flujo 3 — Parseo de PDF con cadena de fallbacks (`parsers.py:_parse_pdf`)

Invocado desde `parse_document` (router de extensión, `parsers.py:718-771`) cuando
`ext == ".pdf"`. Ver el diagrama completo en [`arquitectura.md`](./arquitectura.md);
resumen paso a paso:

1. Si Docling no está instalado (`DOCLING_AVAILABLE=False`, guard de import en
   `parsers.py:35-42`), se va directo a `_parse_image(filepath)` (Vision) — fin del
   flujo.
2. `is_scanned_pdf(filepath)` decide si el PDF es nativo o escaneado
   (RN-EXTRACCIONIA-013).
3. **Si nativo y pdfplumber disponible**: `_extract_native_pdf` extrae tablas página por
   página, fusiona filas fragmentadas (`_merge_fragmented_rows`), detecta y logea
   variantes de encabezado entre páginas (`parsers.py:405-414`), aplica
   `_distribute_brands` (RN-EXTRACCIONIA-015) y convierte a Markdown
   (`_rows_to_markdown`). Si el resultado no está vacío, se devuelve directo — fin del
   flujo.
4. **Si el resultado de pdfplumber está vacío, o pdfplumber levanta una excepción, o el
   PDF es escaneado**: se cae al bloque Docling.
   1. `_split_pdf_by_pages(filepath, pages_per_chunk=15)` (función privada de
      `parsers.py`, distinta de la homónima en `robot_comparativas.py` — ver
      [`arquitectura.md`](./arquitectura.md)).
   2. Por cada chunk (o el archivo completo si no hubo split): `_docling_convert(...,
      lightweight=True)` y `gc.collect()`.
   3. Si un chunk individual falla en Docling, se procesa ese chunk puntual con
      `_parse_image` (Vision) en su lugar — el resto de los chunks sigue por Docling.
   4. Si todo el bloque Docling falla con una excepción no capturada por chunk, se cae a
      `_parse_image(filepath)` sobre el PDF completo (último recurso).
   5. En el `finally`, se hace `gc.collect()` final y se borran los archivos temporales
      de chunk creados en el paso 4.i.
5. El resultado (de cualquiera de las ramas) se normaliza a saltos de línea Unix por
   `parse_document` antes de devolverse al caller (`parsers.py:768`).

`_parse_image` (Vision, usado en los pasos 1, 4.iii y 4.iv) sube el archivo a Gemini,
llama con `_VISION_PROMPT` vía `generate_with_fallback`, reintenta una vez ante
cualquier excepción (2 intentos totales, `parsers.py:653`) y **siempre** borra el
archivo subido a Gemini en el `finally`, incluso si la extracción falló
(`parsers.py:678-690`).
