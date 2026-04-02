# Specification: Parser Router + Comparatives Refactoring

## Overview

This spec defines the observable behavior, data contracts, and acceptance criteria for the Parser Router + Comparatives Refactoring change. It covers the new `app/parsers.py` module (a single `parse_document()` entry point that converts any supported document format to Markdown), the refactored `app/robot_comparativas.py` (two-step Gemini extraction replacing the current single-prompt approach), and the integration changes in `app/main.py`. The spec resolves all open questions left by the proposal, decides the CSV column order and delimiter, and defines error handling, retry behavior, temp file cleanup, and test acceptance criteria with enough precision to make each requirement independently verifiable.

---

## Decisions on Open Questions

The following decisions resolve the open questions from the proposal. They are binding for the design and implementation phases.

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Gemini model for Vision | Use the same `MODEL` instance configured in `config.py` (`gemini-2.5-flash`). | Flash is multimodal. Avoids a second model config. Can be revisited in a dedicated perf change. |
| 2 | Async Step 2 calls | Sequential in this iteration. | Simpler, easier to debug, safer for error handling. Parallelism is a follow-up. |
| 3 | CSV delimiter | Semicolon (`;`) — same as the current output. | Preserving the delimiter avoids breaking downstream consumers (the `/descargar` endpoint streams the file directly to the user's browser). |
| 4 | docling vs PyMuPDF | Use docling as proposed. PyMuPDF is an alternative if docling causes install issues on Windows; document as a known fallback option in requirements. | Docling produces richer Markdown (table structure). PyMuPDF is a future optimization if footprint matters. |
| 5 | Logging infrastructure | Use `logging.getLogger(__name__)` with no extra configuration in this change. No handlers or formatters added. Defer structured logging to a future change. | Minimal scope. The default Python logging config is sufficient for debugging during development. |
| 6 | `robot.py` migration | Out of scope for this change. `robot.py` remains unchanged. | Proposal is explicit: contain blast radius. |
| 7 | CSV column order | NEW order: `renglon;descripcion;proveedor;marca;precio;cliente`. The field `origen` is renamed to `cliente` to match what the code already calls it internally. | `origen` in the current schema is misleading — it holds the client/hospital name extracted from the filename. `cliente` is the correct semantic name. This is a documented breaking change. |

---

## Functional Requirements

### Parser Router (`app/parsers.py`)

**Public API:**

- MUST expose exactly one public function: `parse_document(filepath: Path) -> str`.
- MUST accept a `pathlib.Path` object as the only argument.
- MUST return a `str` containing the document content formatted as Markdown (UTF-8, Unix line endings `\n`).
- MUST route by file extension (case-insensitive). The routing table is:

  | Extension(s) | Handler | Output |
  |---|---|---|
  | `.xlsx`, `.xls` | `_parse_excel()` | Markdown table |
  | `.ods` | `_parse_ods()` | Markdown table |
  | `.pdf` | `_parse_pdf()` | Markdown (docling), with fallback to Gemini Vision if text quality is low |
  | `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif` | `_parse_image()` | Markdown (Gemini Vision) |
  | `.html`, `.htm` | `_parse_html()` | Clean Markdown text (docling or BeautifulSoup4) |
  | anything else | — | Raise `UnsupportedFormatError` |

**Excel / ODS parsing:**

- MUST read the file with `header=None` (no assumed header row) to preserve the raw document structure.
- `.xlsx` MUST use the `openpyxl` engine. `.xls` MUST use the `xlrd` engine. `.ods` MUST use the `odf` engine.
- MUST convert the resulting DataFrame to a Markdown table using `DataFrame.to_markdown(index=False)`.
- If the DataFrame is empty (0 rows after reading), MUST return an empty string `""` rather than a header-only table.
- MUST handle `NaN` values: replace with empty string before rendering the Markdown table.

**PDF parsing:**

- MUST attempt native text extraction via docling first.
- MUST classify the PDF as "scanned" if the average extracted character count per page is **below 50 characters**. The threshold is: `total_chars / max(1, page_count) < 50`.
- If classified as native: MUST return the docling-extracted Markdown directly.
- If classified as scanned (or if docling raises any exception during extraction): MUST fall back to `_parse_image()` (Gemini Vision path).
- MUST attempt to import docling at module load time. If `ImportError` occurs, MUST log a WARNING and treat ALL PDFs as scanned (always fall back to Gemini Vision). This covers Windows install failures.

**Image parsing (Gemini Vision):**

- MUST upload the file using `genai.upload_file(str(filepath))`.
- MUST send the uploaded file to Gemini with the following prompt (exact text):
  ```
  Extract all text from this document. Preserve table structure as Markdown tables. Return only the extracted text with no additional commentary.
  ```
- MUST delete the uploaded file from Gemini storage via `genai.delete_file(uploaded_file.name)` in a `finally` block, regardless of whether the extraction succeeds or raises.
- MUST retry the upload + extraction once on `Exception` before re-raising. (Total: 2 attempts.)
- MUST return the raw text response from Gemini as a string.

**HTML parsing:**

- MUST attempt docling HTML-to-Markdown conversion first.
- If docling raises, MUST fall back to BeautifulSoup4: parse the HTML, extract `soup.get_text(separator="\n")`, strip leading/trailing whitespace per line, collapse consecutive blank lines to one.
- MUST return the resulting plain text as a string.

**Error handling:**

- MUST define `UnsupportedFormatError(extension: str)` as a custom exception inheriting from `ValueError`. The error message MUST be: `"Unsupported file format: '{extension}'"`.
- MUST define `ParserError(filepath: Path, cause: Exception)` as a custom exception inheriting from `RuntimeError`. The error message MUST be: `"Failed to parse '{filepath.name}': {cause}"`. The original exception MUST be chained (`raise ParserError(...) from cause`).
- All internal exceptions from pandas, docling, BeautifulSoup4, or the `genai` SDK MUST be caught and re-raised as `ParserError`, except for `UnsupportedFormatError` which propagates directly.

---

### Comparatives Extraction (`app/robot_comparativas.py`)

**Public API — unchanged signature:**

```python
def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
) -> Path:
```

- MUST return a `Path` pointing to the generated CSV file, identical contract to the current implementation.
- MUST NOT change the function signature or return type.

**Processing pipeline — five stages:**

1. **Parse**: call `parse_document(ruta_archivo)` to get `markdown: str`.
2. **Client**: call `obtener_cliente(nombre_base)` to get `cliente: str`.
3. **Step 1 — Detect providers**: call `_detectar_proveedores(markdown)` → `list[str]`.
4. **Step 2 — Extract per provider**: for each provider in the list, call `_extraer_datos_proveedor(markdown, provider)` → `dict`. Iterate sequentially.
5. **Assembly + CSV export**: merge all per-provider results, add `cliente` field, clean prices, write CSV.

**Step 1 — Detect providers (`_detectar_proveedores`):**

- MUST send the Markdown to Gemini with a prompt requesting JSON in the shape:
  ```json
  {"proveedores": ["Proveedor A", "Proveedor B"]}
  ```
- MUST call `_llamar_gemini_json()` internally.
- MUST return the `proveedores` list as `list[str]`.
- If the list is empty after a successful JSON parse, MUST raise `NoProvidersDetectedError`.
- MUST define `NoProvidersDetectedError` inheriting from `ValueError`. Message: `"No providers detected in document '{filepath.name}'. The document may not be a valid price comparison, or the format is unrecognized."` (the filepath is passed in from `procesar_comparativa`).

**Step 2 — Extract per provider (`_extraer_datos_proveedor`):**

- MUST send the Markdown + provider name to Gemini with a prompt requesting JSON in the shape defined in the Data Contracts section.
- MUST call `_llamar_gemini_json()` internally.
- MUST return the parsed `dict` directly.
- If one provider's extraction fails after all retries, MUST log an ERROR and continue with the remaining providers (fail-partial, not fail-all). The failed provider's rows are simply absent from the final CSV.

**JSON helper (`_llamar_gemini_json`):**

- MUST have signature: `_llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict`.
- MUST strip Markdown code fences from the response before JSON parsing. Specifically:
  - Strip leading ` ```json ` or ` ``` ` (with optional newlines).
  - Strip trailing ` ``` ` (with optional newlines).
- MUST use `re.sub` as shown in the proposal code.
- On `json.JSONDecodeError`, MUST log a WARNING: `"JSON parse failed (attempt {n}), retrying..."`.
- After exhausting all retries, MUST log an ERROR: `"Failed to parse JSON after {max_retries + 1} attempts: {raw[:200]}"` and re-raise the `JSONDecodeError`.

**Price cleaning (`_limpiar_precio`):**

- MUST have signature: `_limpiar_precio(raw: str) -> str`.
- MUST return empty string `""` if `raw` is `None`, empty, or (case-insensitive) any of: `"-"`, `"N/A"`, `"n/a"`, `"no cotiza"`, `"No cotiza"`, `"sin precio"`, `"s/p"`.
- MUST strip currency symbols (`$`, `€`, `USD`, `ARS`, `€`, whitespace) before parsing.
- MUST handle Argentine/Latin American thousand-separator format: `"1.234,56"` → `"1234.56"`.
- MUST handle US/standard format: `"1,234.56"` → `"1234.56"`.
- MUST handle comma-only decimal: `"12,34"` → `"12.34"`.
- MUST return the value formatted as `f"{value:.2f}"` (two decimal places, dot separator) on success.
- On `ValueError` (unparseable after cleaning), MUST log a WARNING: `"Non-numeric price, leaving empty: '{raw}'"` and return `""`.

**Assembly:**

- MUST produce one row per `(renglon, proveedor)` combination.
- MUST add a `cliente` field to every row with the value from `obtener_cliente()`.
- MUST apply `_limpiar_precio()` to every `precio` value.
- MUST NOT include rows where the cleaned price is empty AND no `marca` is present AND no `descripcion` is present (fully empty rows).
- MUST number `renglon` sequentially (1, 2, 3, …) if the value is missing or not a positive integer in the Step 2 response.

**CSV export:**

- MUST write to the output directory using the same `get_output_dir()` + `nombre_unico()` pattern as the current implementation.
- MUST use semicolon (`;`) as the delimiter.
- MUST write UTF-8 encoding, NO BOM (`encoding="utf-8"`, not `"utf-8-sig"`).
- MUST write the header row: `renglon;descripcion;proveedor;marca;precio;cliente`.
- MUST write one data row per assembled result.
- MUST move the source file to `get_processed_dir()` on success, using `nombre_unico()` to avoid collisions.

---

### Integration (`app/main.py`)

- The `/procesar` endpoint MUST NOT change its signature: `POST /procesar`, `multipart/form-data`, fields `archivo` (file) and `tipo` (string).
- The endpoint MUST return `HTMLResponse` using the `index.html` template with either `resultado` or `error` in the context — identical to the current behavior.
- The `/descargar/{nombre_archivo}` endpoint MUST NOT change.
- MUST add `import logging` and `logger = logging.getLogger(__name__)` at module level.
- MUST replace the bare `except Exception as e:` with a block that calls `logger.exception("Error procesando archivo")` before returning the error template response.
- MUST add a `finally` block inside the `/procesar` handler that deletes the temp file (`destino`) if it still exists on disk after processing. This handles the case where `procesar_comparativa()` raises before the file is moved.

---

## Scenarios

### Parser Router Scenarios

#### Scenario: Excel file (.xlsx) with header and data rows
```
Given: An .xlsx file with 1 header-like row and 5 data rows across 3 columns
When: parse_document(filepath) is called
Then: Returns a Markdown string
  AND the string contains a pipe-delimited table with 6 rows (1 header + 5 data)
  AND no NaN or "nan" values appear in the output (replaced with "")
  AND the string encoding is UTF-8
  AND line endings are \n (Unix)
```

#### Scenario: Excel file (.xls) — old format
```
Given: An .xls file (pre-2007 Excel format)
When: parse_document(filepath) is called
Then: The xlrd engine is used (not openpyxl)
  AND a Markdown table is returned
  AND no exception is raised
```

#### Scenario: ODS spreadsheet
```
Given: An .ods file with tabular data
When: parse_document(filepath) is called
Then: The odf engine is used
  AND a Markdown table is returned
```

#### Scenario: HTML file
```
Given: An .html file with embedded tables and paragraph text
When: parse_document(filepath) is called
Then: Returns plain text or Markdown without raw HTML tags
  AND no <div>, <span>, <table>, <td> tags appear in the output
```

#### Scenario: Native PDF (high text density)
```
Given: A PDF file with 3 pages, each containing at least 200 characters of text
When: parse_document(filepath) is called
  AND docling extracts text with average >= 50 chars/page
Then: The docling Markdown output is returned directly
  AND genai.upload_file() is NOT called
```

#### Scenario: Scanned PDF (low text density — fallback)
```
Given: A PDF file where docling extracts < 50 chars/page on average
When: parse_document(filepath) is called
Then: The Gemini Vision fallback is triggered
  AND genai.upload_file() is called exactly once
  AND the extraction prompt is sent to Gemini
  AND genai.delete_file() is called exactly once in a finally block
  AND the Markdown text from Gemini is returned
```

#### Scenario: Scanned PDF — docling raises on import
```
Given: docling is not installable (ImportError at module load)
  AND a PDF file is passed to parse_document()
When: parse_document(filepath) is called
Then: A WARNING is logged at module load time: "docling not available..."
  AND ALL PDFs fall back to Gemini Vision path
  AND no exception propagates to the caller for the import failure itself
```

#### Scenario: Image file (.jpg, .png, .tiff)
```
Given: An image file in any of the supported image formats
When: parse_document(filepath) is called
Then: genai.upload_file() is called with the file path
  AND the extraction prompt is sent
  AND genai.delete_file() is called in a finally block
  AND the text content is returned as a string
```

#### Scenario: Gemini Vision cleanup on extraction error
```
Given: An image file is uploaded to Gemini successfully
  AND Gemini raises an exception during generate_content()
  AND this is the second attempt (retry exhausted)
When: parse_document(filepath) is called
Then: genai.delete_file() is called exactly once (in the finally block)
  AND the exception is re-raised as ParserError
```

#### Scenario: Unsupported format
```
Given: A file with extension .zip, .docx, .pptx, or any other unsupported format
When: parse_document(filepath) is called
Then: UnsupportedFormatError is raised
  AND the error message contains the actual extension
  AND no Gemini API call is made
```

---

### Comparatives Extraction Scenarios

#### Scenario: Valid multi-provider document
```
Given: A document (any format) containing 3 providers and 10 items each
  AND filename follows the pattern "HOSPITAL_comparativa_2024.xlsx"
When: procesar_comparativa(filepath, nombre_original) is called
Then: parse_document() is called once and returns Markdown
  AND Step 1 detects all 3 providers (list length = 3)
  AND Step 2 is called 3 times (once per provider)
  AND Assembly produces 30 rows (10 items × 3 providers)
  AND every row has "cliente" = "HOSPITAL"
  AND CSV is written with 31 lines (1 header + 30 data rows)
  AND the source file is moved to Procesados/
  AND the returned Path points to the generated CSV file
```

#### Scenario: Document with 1 provider
```
Given: A document with exactly 1 provider and 5 items
When: procesar_comparativa(filepath, nombre_original) is called
Then: Step 1 returns list of length 1
  AND Step 2 is called exactly once
  AND CSV has 6 lines (header + 5 rows)
```

#### Scenario: Gemini returns invalid JSON on first attempt, valid on retry
```
Given: The first Gemini response for Step 1 is malformed JSON (e.g. missing closing bracket)
  AND the second response is valid JSON with 2 providers
When: _llamar_gemini_json(prompt, markdown) is called (max_retries=2)
Then: First attempt raises json.JSONDecodeError internally
  AND a WARNING is logged: "JSON parse failed (attempt 1), retrying..."
  AND Gemini is called again (second attempt)
  AND the valid JSON dict is returned
  AND no exception propagates
```

#### Scenario: Gemini returns invalid JSON on all attempts
```
Given: All 3 Gemini responses (1 initial + 2 retries) are malformed JSON
When: _llamar_gemini_json(prompt, markdown, max_retries=2) is called
Then: 3 total Gemini calls are made
  AND WARNING is logged for attempts 1 and 2
  AND ERROR is logged for final failure, including first 200 chars of raw response
  AND json.JSONDecodeError is re-raised
```

#### Scenario: Gemini returns JSON wrapped in code fences
```
Given: Gemini returns:
  ```json
  {"proveedores": ["A", "B"]}
  ```
When: _llamar_gemini_json() processes this response
Then: The code fences are stripped
  AND json.loads() succeeds on the first attempt
  AND the dict {"proveedores": ["A", "B"]} is returned
```

#### Scenario: No providers detected in Step 1
```
Given: A document that does not contain recognizable provider names
  AND Step 1 returns {"proveedores": []}
When: procesar_comparativa(filepath, nombre_original) is called
Then: NoProvidersDetectedError is raised
  AND the error message contains the filename
  AND no CSV file is written
  AND the temp file is cleaned up (finally block in main.py deletes it)
```

#### Scenario: Step 2 fails for one provider but succeeds for others
```
Given: A document with 3 providers
  AND Step 2 raises JSONDecodeError for provider "Proveedor B" after all retries
When: procesar_comparativa(filepath, nombre_original) is called
Then: ERROR is logged for provider "Proveedor B"
  AND Step 2 continues for "Proveedor A" and "Proveedor C"
  AND CSV is written with rows from providers A and C only
  AND no exception propagates from procesar_comparativa()
  AND the source file is moved to Procesados/
```

#### Scenario: Price cleaning — Argentine format
```
Given: precio field contains "$1.234,56"
When: _limpiar_precio("$1.234,56") is called
Then: Returns "1234.56"
```

#### Scenario: Price cleaning — US format
```
Given: precio field contains "1,234.56"
When: _limpiar_precio("1,234.56") is called
Then: Returns "1234.56"
```

#### Scenario: Price cleaning — comma decimal
```
Given: precio field contains "12,34"
When: _limpiar_precio("12,34") is called
Then: Returns "12.34"
```

#### Scenario: Price cleaning — non-cotizable values
```
Given: precio is any of: "-", "N/A", "no cotiza", "No cotiza", "sin precio", "s/p", ""
When: _limpiar_precio(raw) is called
Then: Returns "" in all cases
```

#### Scenario: Price cleaning — currency symbols
```
Given: precio field contains "$ 500.00" or "USD 500" or "ARS 500,00"
When: _limpiar_precio(raw) is called
Then: Returns "500.00" (currency prefix stripped)
```

#### Scenario: Price cleaning — unparseable string
```
Given: precio field contains "consultar" or "a convenir"
When: _limpiar_precio(raw) is called
Then: Returns ""
  AND a WARNING is logged: "Non-numeric price, leaving empty: 'consultar'"
```

#### Scenario: obtener_cliente extracts from filename
```
Given: nombre_original is "HOSPITAL_ITALIANO_comparativa_2024.pdf"
When: procesar_comparativa() derives nombre_base = "HOSPITAL_ITALIANO_comparativa_2024"
  AND obtener_cliente(nombre_base) is called
Then: Returns "HOSPITAL" (the prefix before the first underscore)
```

#### Scenario: CSV output format verification
```
Given: Assembly produces 3 rows with all fields populated
When: CSV is written to disk
Then: First line is exactly "renglon;descripcion;proveedor;marca;precio;cliente"
  AND subsequent lines use ";" as delimiter
  AND empty marca field is "" (not "NaN", not "N/A", not "null")
  AND precio field is "1234.56" format (numeric, 2 decimals, dot separator)
  AND file is UTF-8 encoded with no BOM
```

---

### Integration Scenarios

#### Scenario: Successful comparativas upload via /procesar
```
Given: User uploads a valid comparativas file via POST /procesar
  AND tipo = "comparativas"
When: The endpoint processes the file
Then: procesar_comparativa() is called with the temp file path
  AND a "resultado" URL is included in the template context
  AND the response is HTTP 200 with HTMLResponse
  AND the temp file no longer exists (cleaned up by finally block)
```

#### Scenario: Error during comparativas processing
```
Given: procesar_comparativa() raises NoProvidersDetectedError
When: The /procesar endpoint catches the exception
Then: logger.exception() is called (logs full traceback)
  AND an "error" key is in the template context
  AND the response is HTTP 200 with HTMLResponse (error shown in UI)
  AND the temp file is deleted by the finally block
```

#### Scenario: Temp file cleanup on success
```
Given: procesar_comparativa() succeeds and moves the file to Procesados/
When: The finally block in /procesar runs
Then: It checks if the temp file path still exists
  AND since the file was moved, no deletion occurs (no FileNotFoundError raised)
```

#### Scenario: Temp file cleanup on error
```
Given: procesar_comparativa() raises before moving the file
When: The finally block in /procesar runs
Then: The temp file still exists at the temp path
  AND the finally block calls destino.unlink(missing_ok=True)
  AND the temp file is deleted
```

---

## Data Contracts

### `parse_document()` return format

The returned Markdown string MUST conform to the following rules:

**For spreadsheet sources (Excel, ODS):**
```
| col0 | col1 | col2 |
|------|------|------|
| val1 | val2 | val3 |
| val4 | val5 |      |
```
- Pipe-delimited table format (standard pandas `to_markdown()` output).
- Header row is the first DataFrame row (since `header=None` is used, columns are `0, 1, 2, ...` unless the file has actual headers in row 0).
- `NaN` values replaced with empty string before rendering.

**For text/PDF/HTML/image sources:**
- Free-form Markdown text.
- No HTML tags (`<div>`, `<span>`, `<table>`, etc.) in the output.
- Paragraph breaks as double `\n`.
- Tables preserved in pipe-delimited format where the source has tabular content.

**Common constraints:**
- Encoding: UTF-8 (Python string — encoding is at the caller's discretion when writing to disk).
- Line endings: `\n` (Unix). No `\r\n`.
- Trailing newline: NOT guaranteed. Callers MUST NOT rely on or strip a trailing newline.

---

### Gemini Step 1 output — Detect Providers

```json
{
  "proveedores": [
    "Nombre completo proveedor A",
    "Nombre completo proveedor B"
  ]
}
```

Constraints:
- Root object MUST have exactly one key: `"proveedores"`.
- `"proveedores"` MUST be an array of strings.
- Each string is the provider's name as it appears in the document.
- An empty array (`[]`) is valid JSON but triggers `NoProvidersDetectedError`.
- No other fields are required or expected.

---

### Gemini Step 2 output — Extract Per Provider

```json
{
  "proveedor": "Nombre completo proveedor A",
  "renglones": [
    {
      "renglon": 1,
      "descripcion": "Amoxicilina 500mg x 30 comprimidos",
      "marca": "Roemmers",
      "precio": "1234.56"
    },
    {
      "renglon": 2,
      "descripcion": "Ibuprofeno 400mg x 20 comprimidos",
      "marca": "",
      "precio": "no cotiza"
    }
  ]
}
```

Constraints:
- `"proveedor"`: string, MUST match (or closely match) the input provider name.
- `"renglones"`: array of objects, MAY be empty (empty array treated as no data for this provider).
- Per-renglon fields:
  - `"renglon"`: integer or string representing the item number. Assembly will re-number if missing or non-positive.
  - `"descripcion"`: string. Empty string if no description available.
  - `"marca"`: string. Empty string if no brand information. MUST NOT be `null` or absent — the prompt must enforce this. If absent in the response, Assembly treats it as `""`.
  - `"precio"`: string (pre-cleaned by Gemini best effort, but `_limpiar_precio()` is applied in Assembly regardless). May be `"no cotiza"`, `"-"`, a numeric string, or a formatted number like `"$1.234,56"`.

---

### CSV output format

```
renglon;descripcion;proveedor;marca;precio;cliente
1;Amoxicilina 500mg x 30 comprimidos;Drogueria del Sud;Roemmers;1234.56;HOSPITAL
2;Ibuprofeno 400mg x 20 comprimidos;Drogueria del Sud;;899.00;HOSPITAL
1;Amoxicilina 500mg x 30 comprimidos;Farmacia Central;Bago;1150.00;HOSPITAL
```

Constraints:
- Delimiter: `;` (semicolon).
- Encoding: UTF-8, no BOM.
- Line endings: `\n` (Unix). The file MUST end with a trailing `\n`.
- Column order (fixed): `renglon`, `descripcion`, `proveedor`, `marca`, `precio`, `cliente`.
- `renglon`: positive integer as string (e.g., `"1"`, `"12"`).
- `descripcion`: free text, no semicolons (if a semicolon appears in description, it SHOULD be stripped or replaced with a space to avoid CSV parsing errors).
- `proveedor`: free text, no semicolons.
- `marca`: empty string if absent (not `"NaN"`, not `"N/A"`, not `"null"`).
- `precio`: numeric string with 2 decimal places and dot separator (e.g., `"1234.56"`), OR empty string `""`.
- `cliente`: string extracted from filename via `obtener_cliente()`.
- No quoting of fields (current behavior, preserved).

**BREAKING CHANGE note**: The column order and `origen` → `cliente` rename differ from the current output (`renglon;descripcion;marca;proveedor;precio;origen`). Any downstream consumer that reads the CSV by column index (not by header name) will break. Consumers that read by header name will need to handle the renamed `origen` → `cliente` column.

---

### Custom Exceptions

| Exception | Inherits | Constructor | Message format |
|-----------|----------|-------------|----------------|
| `UnsupportedFormatError` | `ValueError` | `(extension: str)` | `"Unsupported file format: '{extension}'"` |
| `ParserError` | `RuntimeError` | `(filepath: Path, cause: Exception)` | `"Failed to parse '{filepath.name}': {cause}"` |
| `NoProvidersDetectedError` | `ValueError` | `(filepath: Path)` | `"No providers detected in document '{filepath.name}'. The document may not be a valid price comparison, or the format is unrecognized."` |

All three MUST be importable from `app.parsers` (`UnsupportedFormatError`, `ParserError`) and `app.robot_comparativas` (`NoProvidersDetectedError`).

---

## Edge Cases & Constraints

### Empty document (0 bytes or 0 rows)
- A file with 0 bytes: `_parse_image()` will upload an empty file. Gemini will likely return an empty or minimal string. `parse_document()` MUST return `""` in this case (no exception). Callers are responsible for handling empty Markdown.
- An Excel file with 0 data rows: `parse_document()` MUST return `""` (not a header-only table). Step 1 receiving empty Markdown will likely return an empty providers list, triggering `NoProvidersDetectedError`. This is the correct behavior.
- An HTML file with no text content: `parse_document()` MUST return `""`.

### Very large documents (>50MB)
- No size check is implemented in this change. Files are processed as-is.
- `genai.upload_file()` has its own size limits (Gemini API limit: ~20MB for inline, larger via File API). If the upload fails due to size, the `genai` SDK raises an exception, which `_parse_image()` catches and wraps as `ParserError`.
- This is an accepted limitation for this iteration. A size guard can be added in a follow-up.

### Document with 0 providers
- Step 1 returns `{"proveedores": []}`.
- `_detectar_proveedores()` raises `NoProvidersDetectedError`.
- No CSV is written.
- The error propagates to `main.py`, which logs it and returns an error template response.
- The finally block in `main.py` deletes the temp file.

### Document with 1 provider
- Normal path. Step 2 is called once.
- CSV has N rows where N = number of renglones for that provider.

### Document with many providers (e.g., 50)
- Step 2 is called 50 times sequentially.
- No parallelism in this iteration.
- Expected total latency: up to 400 seconds (50 × 8s). See Performance section.
- No special handling. This is an accepted constraint for this iteration.

### Price in different currencies
- Currency symbols are stripped: `$`, `€`, and the strings `"USD"`, `"ARS"`, `"€"` and surrounding whitespace.
- No currency conversion is performed. Prices are normalized to a numeric string only.
- Example: `"USD 1500.00"` → `"1500.00"`. `"ARS 1.500,00"` → `"1500.00"`.

### Gemini returns HTML instead of JSON
- The `_llamar_gemini_json()` function will fail on `json.loads()`.
- The retry mechanism kicks in (up to 2 retries).
- If all attempts return HTML, `JSONDecodeError` is raised and logged.
- For Step 1: `procesar_comparativa()` fails, temp file is cleaned up, error shown in UI.
- For Step 2 (one provider): that provider's data is absent from the CSV; processing continues.

### Gemini returns JSON with extra text before/after
- The code fence stripping regex handles ` ```json ... ``` ` wrapping.
- If Gemini returns `"Here is the JSON: {...}"` (extra prose), `json.loads()` will fail.
- The retry mechanism applies. This is a known fragility — the prompt engineering must constrain Gemini to return ONLY JSON.

### Temp file missing at cleanup (already moved or deleted)
- The finally block in `main.py` MUST use `Path.unlink(missing_ok=True)` to avoid `FileNotFoundError` when the file was already moved by `procesar_comparativa()` on success.

### docling not installed on Windows
- If `import docling` raises `ImportError` at module load time in `parsers.py`, a WARNING is logged.
- A module-level flag `DOCLING_AVAILABLE = False` is set.
- `_parse_pdf()` checks this flag and routes all PDFs directly to `_parse_image()`.
- No user-visible error. The behavior is functionally equivalent to treating all PDFs as scanned.

### Gemini API rate limiting (429)
- The `genai` SDK raises an exception.
- `_llamar_gemini_json()` does NOT add retry logic for API errors (only for JSON parse errors).
- The exception propagates to `procesar_comparativa()` → `main.py`.
- `main.py` logs the full traceback and returns the error to the UI.
- Fail-fast behavior for API errors. Retry on network/rate errors is a future concern.

### Filename without underscore (no client prefix)
- `obtener_cliente("SINPREFIJO.pdf")` returns `"SINPREFIJO"` (the entire stem, since `split("_", 1)[0]` returns the whole string when there's no underscore). This is the current behavior and is preserved.

---

## Backward Compatibility

### FastAPI endpoints — PRESERVED
- `POST /procesar`: signature, input format, response format — all unchanged.
- `GET /descargar/{nombre_archivo}`: unchanged.
- Template context keys (`resultado`, `error`, `tipo`) — unchanged.

### CSV column order — BREAKING CHANGE
| | Current | New |
|---|---------|-----|
| Column 1 | `renglon` | `renglon` |
| Column 2 | `descripcion` | `descripcion` |
| Column 3 | `marca` | `proveedor` |
| Column 4 | `proveedor` | `marca` |
| Column 5 | `precio` | `precio` |
| Column 6 | `origen` | `cliente` |

The column order changes (columns 3 and 4 swap) and the last column is renamed from `origen` to `cliente`.

**Impact assessment:**
- The `/descargar` endpoint streams the CSV file as `text/csv` without any transformation. Downstream consumers that import CSVs by header name are unaffected by the column order swap but must handle the `origen` → `cliente` rename.
- Consumers that read by column index (e.g., spreadsheets importing the CSV with fixed column mappings) will see incorrect data in columns 3 and 4.
- This change is intentional. The new column order matches the two-step extraction data model more naturally (`proveedor` before `marca`). The rename from `origen` to `cliente` eliminates a misleading field name.

### `robot.py` — UNCHANGED
- `procesar_archivo()`, `obtener_cliente()`, `nombre_unico()` — all unchanged.
- `robot.py` does NOT use `parsers.py`. Zero regression risk.

---

## Performance & Reliability

### Two-Step Extraction Latency Budget

| Step | Estimated latency | Basis |
|------|------------------|-------|
| `parse_document()` — Excel/ODS | < 1 second | Local pandas read |
| `parse_document()` — native PDF | 2–8 seconds | docling conversion |
| `parse_document()` — scanned PDF / image | 3–10 seconds | Gemini Vision upload + inference |
| Step 1: detect providers | 2–5 seconds | Single Gemini call |
| Step 2 per provider | 3–8 seconds | Single Gemini call |
| Assembly + CSV write | < 0.5 seconds | Pure Python |

**Total budget for a typical document (3 providers):**
- Parse: ~5s + Step 1: ~3s + Step 2 (3 × 5s): ~15s = ~23 seconds.
- **SLA: comparatives processing SHOULD complete within 90 seconds.**
- For unusually large documents with many providers (>10), completion time MAY exceed 90 seconds. No timeout is enforced in this iteration.

### JSON Parse Retry Policy

- Maximum retries: 2 (3 total attempts: 1 initial + 2 retries).
- Retry applies only to `json.JSONDecodeError` (malformed response).
- No delay between retries (immediate re-call to Gemini).
- API errors (network failures, 429 rate limit, SDK exceptions other than JSON parse) are NOT retried — they fail fast.

### Temp File Lifecycle

| Event | What happens to the temp file |
|---|---|
| procesar_comparativa() succeeds | File is moved to `Procesados/` by `shutil.move()` inside `robot_comparativas.py`. The finally block in `main.py` finds the file gone and takes no action. |
| procesar_comparativa() raises before moving | File remains in `tmp/`. The finally block in `main.py` calls `destino.unlink(missing_ok=True)` to delete it. |
| Unexpected crash (process killed) | File remains in `tmp/`. No automatic cleanup. Manual cleanup required. |

- Cleanup is **synchronous**, occurring before the HTTP response is returned.
- Temp files are stored at `{OUTPUT_BASE}/{origen}/tmp/{uuid}_{filename}`.
- No TTL-based cleanup (e.g., cron or background task) is in scope for this change.

### Gemini File Store Cleanup

- Files uploaded via `genai.upload_file()` (Vision path) MUST be deleted via `genai.delete_file()` in a `finally` block.
- This applies to both `_parse_image()` in `parsers.py` and any legacy usage in `robot_comparativas.py`.
- Failure to delete (e.g., `genai.delete_file()` raises) MUST be logged as a WARNING but MUST NOT suppress the original exception or prevent the response from being returned.

---

## Testing Acceptance Criteria

### Parser Router Tests (`tests/test_parsers.py`) — 9 tests required

All tests use mocked dependencies. No real Gemini API calls. No real docling calls in PDF/image tests.

| Test name | What it verifies |
|---|---|
| `test_parse_excel_xlsx` | `.xlsx` → Markdown table contains all rows; `NaN` replaced with `""` |
| `test_parse_excel_xls` | `.xls` → `xlrd` engine used; Markdown returned |
| `test_parse_ods` | `.ods` → `odf` engine used; Markdown returned |
| `test_parse_html` | `.html` → no HTML tags in output; plain text or Markdown returned |
| `test_parse_pdf_native` | Native PDF (>= 50 chars/page) → docling called; `genai.upload_file` NOT called |
| `test_parse_pdf_scanned_fallback` | Scanned PDF (< 50 chars/page) → docling called first, Gemini Vision called second |
| `test_parse_image_formats` | `.jpg`, `.png`, `.tiff` all route to `_parse_image()`; Gemini called; text returned |
| `test_unsupported_format` | `.zip` → `UnsupportedFormatError` raised; message contains ".zip" |
| `test_gemini_vision_cleanup` | `genai.upload_file()` called; `generate_content()` raises; `genai.delete_file()` still called |

**Test infrastructure:**
- Real Excel, ODS, and HTML files MUST be created using `pytest`'s `tmp_path` fixture (using `openpyxl`, `pandas`, or raw strings).
- Gemini SDK (`genai.upload_file`, `genai.delete_file`, `MODEL.generate_content`) MUST be mocked via `pytest-mock` (`mocker.patch`).
- docling calls MUST be mocked via `unittest.mock.patch`.

### Comparatives Tests (`tests/test_robot_comparativas.py`) — 9 tests required

All tests mock Gemini. No real API calls.

| Test name | What it verifies |
|---|---|
| `test_detect_providers` | `_detectar_proveedores()` correctly parses `{"proveedores": ["A", "B"]}` → returns `["A", "B"]` |
| `test_extract_per_provider` | `_extraer_datos_proveedor()` correctly parses Step 2 JSON → returns dict with `renglones` list |
| `test_assembly_adds_fields` | Assembly adds `proveedor` and `cliente` fields to every row |
| `test_price_cleaning` | `_limpiar_precio("$1.234,56")` → `"1234.56"`, `_limpiar_precio("1,234.56")` → `"1234.56"` |
| `test_price_cleaning_invalid` | `_limpiar_precio("no cotiza")` → `""`, `_limpiar_precio("consultar")` → `""` with WARNING logged |
| `test_retry_on_invalid_json` | First Gemini call returns bad JSON; second returns good JSON; result is the good dict; 2 total Gemini calls |
| `test_no_providers_raises` | Empty providers list → `NoProvidersDetectedError` raised with filepath in message |
| `test_cliente_from_filename` | `"HOSPITAL_ITALIANO_2024.pdf"` → `obtener_cliente("HOSPITAL_ITALIANO_2024")` → `"HOSPITAL"` |
| `test_csv_output_format` | Final CSV has header `renglon;descripcion;proveedor;marca;precio;cliente`; semicolon delimiter; UTF-8; no BOM |

### Shared Fixtures (`tests/conftest.py`)

- `gemini_model_mock`: patches `app.config.MODEL.generate_content` to return a `MagicMock` with `.text` attribute.
- `genai_upload_mock`: patches `google.generativeai.upload_file`.
- `genai_delete_mock`: patches `google.generativeai.delete_file`.

### Coverage requirement

All tests MUST pass. Target: **100% line coverage** of `app/parsers.py` and the new logic in `app/robot_comparativas.py`. Coverage MUST be measured via `pytest-cov` or `coverage.py`.

### Test runner invocation

```
pytest tests/ -v --tb=short
```

No test MUST make real network calls. The test suite MUST be runnable offline (with mocks).
