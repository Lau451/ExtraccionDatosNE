# Design: Parser Router + Comparatives Refactoring

## Architecture Overview

This design transforms the comparatives processing pipeline from a monolithic single-prompt approach into a layered architecture with three distinct responsibilities:

1. **Format normalization** (`app/parsers.py`) -- Converts any supported document format into a uniform Markdown string. Pure I/O + format conversion. No AI extraction logic.
2. **AI-driven extraction** (`app/robot_comparativas.py`) -- Two-step Gemini pipeline that receives clean Markdown and produces structured data. No file format awareness.
3. **Orchestration** (`app/main.py`) -- HTTP handling, temp file lifecycle, error logging. No parsing or extraction logic.

```
                    app/main.py
                   (orchestration)
                        |
                        v
              app/robot_comparativas.py
               (AI extraction pipeline)
                   |            |
                   v            v
            app/parsers.py   app/config.py
          (format normalization)  (MODEL, paths)
                   |
        +----------+----------+----------+----------+
        |          |          |          |          |
     pandas     docling    genai      BS4       (stdlib)
   (Excel/ODS)  (PDF)    (Vision)   (HTML)
```

Key constraint: `app/robot.py` remains UNTOUCHED. It does NOT import `parsers.py`. Zero coupling, zero regression risk.

---

## Module Responsibility Map

### app/parsers.py (NEW)

**Purpose**: Centralized document parsing. Single entry point that accepts any supported file format and returns a Markdown string. The module is a **router**: it detects the format by extension and delegates to the appropriate private handler. No AI extraction logic lives here -- only text/structure extraction.

**Public API**:

```python
def parse_document(filepath: Path) -> str
```

**Private Functions**:

| Function | Responsibility |
|----------|---------------|
| `_parse_excel(filepath: Path) -> str` | Read `.xlsx`/`.xls` via pandas, return Markdown table |
| `_parse_ods(filepath: Path) -> str` | Read `.ods` via pandas (odf engine), return Markdown table |
| `_parse_pdf(filepath: Path) -> str` | Attempt docling extraction; fall back to Vision if scanned |
| `_parse_html(filepath: Path) -> str` | Attempt docling; fall back to BeautifulSoup4 |
| `_parse_image(filepath: Path) -> str` | Upload to Gemini Vision, extract text, cleanup |
| `_is_scanned_pdf(text: str, page_count: int, threshold: int = 50) -> bool` | Heuristic: `total_chars / max(1, page_count) < threshold` |

**Custom Exceptions**:

| Exception | Inherits | Purpose |
|-----------|----------|---------|
| `UnsupportedFormatError` | `ValueError` | Unknown file extension |
| `ParserError` | `RuntimeError` | Wraps any internal parsing failure with filepath context |

**Dependencies**:

| Package | Used in | Purpose |
|---------|---------|---------|
| `pandas` | `_parse_excel`, `_parse_ods` | Read spreadsheets |
| `openpyxl` | via pandas engine | `.xlsx` reading |
| `xlrd` | via pandas engine | `.xls` reading |
| `odfpy` | via pandas engine | `.ods` reading |
| `docling` | `_parse_pdf`, `_parse_html` | Native text/Markdown extraction (optional, guarded import) |
| `beautifulsoup4` | `_parse_html` | HTML fallback parser |
| `google.generativeai` | `_parse_image` | Gemini Vision for images/scanned PDFs |
| `app.config.MODEL` | `_parse_image` | Gemini model instance |
| `logging` | all functions | Structured logging |
| `pathlib.Path` | all functions | File path handling |

---

### app/robot_comparativas.py (MODIFIED)

**Purpose**: Two-step AI extraction pipeline for price comparison documents. Receives a file path, delegates parsing to `parsers.py`, sends clean Markdown through a detect-then-extract Gemini pipeline, and assembles the final CSV.

**Public API** (signature unchanged):

```python
def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
) -> Path
```

**Private Functions**:

| Function | Responsibility |
|----------|---------------|
| `_detectar_proveedores(markdown: str, filepath: Path) -> list[str]` | Step 1: send Markdown to Gemini, parse JSON, return provider list. Raises `NoProvidersDetectedError` if empty. |
| `_extraer_datos_proveedor(markdown: str, proveedor: str) -> dict` | Step 2: extract data for a single provider. Returns structured dict. |
| `_llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict` | Generic Gemini-to-JSON helper with code fence stripping and retry. |
| `_limpiar_precio(raw: str) -> str` | Clean a price string to `"1234.56"` format or `""`. |
| `_ensamblar_csv(providers_data: list[dict], cliente: str) -> list[dict]` | Merge per-provider results, add `cliente`, clean prices, renumber renglones if needed. |

**Custom Exceptions**:

| Exception | Inherits | Purpose |
|-----------|----------|---------|
| `NoProvidersDetectedError` | `ValueError` | Step 1 returned empty provider list |

**Dependencies**:

| Package | Purpose |
|---------|---------|
| `app.parsers.parse_document` | Format normalization (NEW dependency) |
| `app.config.MODEL` | Gemini model instance |
| `app.config.get_output_dir`, `get_processed_dir`, `COMPARATIVAS_OUTPUT_BASE` | Output paths |
| `app.robot.obtener_cliente`, `nombre_unico` | Client extraction, unique filenames (EXISTING) |
| `json` | JSON parsing |
| `re` | Code fence stripping, price cleaning |
| `logging` | Structured logging |
| `csv` | CSV writing (replaces manual string writing) |
| `shutil` | File move to Procesados |
| `pathlib.Path` | File path handling |

**Removed code**: The entire `_PROMPT` constant, all format detection logic (`extension in {".xls", ".xlsx"}`, `genai.upload_file()` fallback), and raw CSV text parsing are DELETED. They are replaced by `parse_document()` + two-step extraction + `_ensamblar_csv()`.

---

### app/main.py (MODIFIED)

**Purpose**: HTTP orchestration. Receives file uploads, delegates to robot modules, handles errors, cleans up temp files.

**Changes from current**:

| Area | Current | New |
|------|---------|-----|
| Logging | None | `import logging` + `logger = logging.getLogger(__name__)` |
| Error handling | Bare `except Exception as e:` | `except Exception:` with `logger.exception("Error procesando archivo")` |
| Temp file cleanup | None | `finally: destino.unlink(missing_ok=True)` |
| Imports | Direct `procesar_comparativa` | Same import (unchanged) |

The call to `procesar_comparativa(destino, nombre_original)` does NOT change. The parser router is internal to `robot_comparativas.py`.

---

## Data Flow

### End-to-End Sequence: Comparatives Processing

```
User uploads file (POST /procesar, tipo="comparativas")
  |
  v
[main.py] Save file to tmp/{uuid}_{filename}
  |
  v
[main.py] procesar_comparativa(destino, nombre_original)
  |
  v
[robot_comparativas.py] Derive nombre_base, extension, cliente
  |
  v
[robot_comparativas.py] markdown = parse_document(ruta_archivo)
  |                                      |
  |                           [parsers.py] Route by extension
  |                                      |
  |                +-----+-----+----+----+-----+
  |                |     |     |    |    |     |
  |              xlsx   xls   ods  pdf  html  image
  |                |     |     |    |    |     |
  |             pandas  pandas pandas docling BS4  Gemini
  |                |     |     |    |    |   Vision
  |                +-----+-----+----+----+-----+
  |                                      |
  |                            Markdown string
  |                                      |
  v  <-----------------------------------+
[robot_comparativas.py] Step 1: _detectar_proveedores(markdown)
  |
  |   Gemini call -> JSON -> {"proveedores": ["A", "B", "C"]}
  |
  v
[robot_comparativas.py] Step 2: loop per provider
  |   _extraer_datos_proveedor(markdown, "A") -> {proveedor, renglones}
  |   _extraer_datos_proveedor(markdown, "B") -> {proveedor, renglones}
  |   _extraer_datos_proveedor(markdown, "C") -> {proveedor, renglones}
  |
  v
[robot_comparativas.py] _ensamblar_csv(all_results, cliente)
  |   Merge, add cliente, clean prices, renumber
  |
  v
[robot_comparativas.py] Write CSV to output_dir
  |
  v
[robot_comparativas.py] shutil.move(source -> Procesados/)
  |
  v
[robot_comparativas.py] Return Path to CSV
  |
  v
[main.py] Return template with download link
  |
  v
[main.py] finally: destino.unlink(missing_ok=True)
```

### Error Flow

```
Error at parse_document()
  |
  ParserError or UnsupportedFormatError propagates up
  |
  v
[main.py] except block: logger.exception(), return error template
  |
  v
[main.py] finally: delete temp file (it was never moved)


Error at Step 1 (empty providers)
  |
  NoProvidersDetectedError propagates up
  |
  v
[main.py] except block: logger.exception(), return error template
  |
  v
[main.py] finally: delete temp file


Error at Step 1 (JSON parse failure, all retries exhausted)
  |
  json.JSONDecodeError propagates up
  |
  v
[main.py] except block: logger.exception(), return error template
  |
  v
[main.py] finally: delete temp file


Error at Step 2 (one provider fails JSON)
  |
  json.JSONDecodeError caught INSIDE the per-provider loop
  |
  v
[robot_comparativas.py] Log ERROR, skip that provider, continue loop
  |
  v
CSV written with remaining providers' data (partial success)
  |
  v
[main.py] Return template with download link (success path)


Error at Gemini API (429, network, SDK)
  |
  Exception propagates immediately (no retry for API errors)
  |
  v
[main.py] except block: logger.exception(), return error template
  |
  v
[main.py] finally: delete temp file
```

---

## Function Interfaces

### parse_document()

```python
def parse_document(filepath: Path) -> str:
    """
    Parse a document of any supported format to Markdown.

    Routes by file extension (case-insensitive) to the appropriate handler.
    All handlers return a UTF-8 string with Unix line endings.

    Args:
        filepath: Path to the document file. Must exist on disk.

    Returns:
        Markdown-formatted string representation of document content.
        Returns empty string "" for empty documents (0 rows, 0 bytes of text).

    Raises:
        FileNotFoundError: If filepath does not exist on disk.
        UnsupportedFormatError: If file extension is not in the supported set.
        ParserError: If the underlying parser (pandas, docling, Gemini, BS4)
            fails. The original exception is chained via `raise ... from cause`.

    Side effects:
        - For images/scanned PDFs: uploads to Gemini API via genai.upload_file(),
          then deletes via genai.delete_file() in a finally block.
        - Reads the file from disk (read-only).
        - No temp files created by this function.

    Guarantees:
        - Always returns a Python str (UTF-8 in-memory).
        - Line endings are \n (Unix style).
        - No Gemini uploaded files left in storage (cleanup in finally).
        - No NaN or "nan" strings in spreadsheet output (replaced with "").
    """
```

**Implementation sketch**:

```python
_EXTENSION_ROUTER: dict[str, Callable] = {
    ".xlsx": _parse_excel,
    ".xls":  _parse_excel,
    ".ods":  _parse_ods,
    ".pdf":  _parse_pdf,
    ".jpg":  _parse_image,
    ".jpeg": _parse_image,
    ".png":  _parse_image,
    ".tiff": _parse_image,
    ".tif":  _parse_image,
    ".html": _parse_html,
    ".htm":  _parse_html,
}

def parse_document(filepath: Path) -> str:
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = filepath.suffix.lower()
    handler = _EXTENSION_ROUTER.get(ext)
    if handler is None:
        raise UnsupportedFormatError(ext)

    try:
        return handler(filepath)
    except (UnsupportedFormatError, ParserError):
        raise
    except Exception as exc:
        raise ParserError(filepath, exc) from exc
```

**Design decision**: The router uses a dict mapping instead of if/elif chains. This is more extensible (adding a format = adding one dict entry), more testable (the dict is inspectable), and avoids the long conditional chain in the current `robot_comparativas.py`.

---

### _parse_excel()

```python
def _parse_excel(filepath: Path) -> str:
    """
    Parse an Excel file (.xlsx or .xls) to a Markdown table.

    Uses openpyxl engine for .xlsx, xlrd for .xls. Reads with header=None
    to preserve raw document structure. NaN values are replaced with empty
    strings before rendering.

    Args:
        filepath: Path to the Excel file.

    Returns:
        Markdown table string. Empty string "" if the DataFrame has 0 rows.

    Raises:
        Exception from pandas (caught by parse_document, wrapped as ParserError).

    Side effects:
        Reads file from disk (read-only).
    """
```

**Implementation detail**: The engine selection is based on the extension, determined inside this function:

```python
engine = "xlrd" if filepath.suffix.lower() == ".xls" else "openpyxl"
df = pd.read_excel(filepath, engine=engine, header=None)
if df.empty:
    return ""
df = df.fillna("")
return df.to_markdown(index=False)
```

**Design decision**: `header=None` is critical. The current code in `robot_comparativas.py` uses `header=None` and converts to CSV. We keep `header=None` but convert to Markdown tables instead. This preserves ALL rows (the first row might be data, not a header) while giving Gemini better structural context than semicolon-separated CSV.

---

### _parse_ods()

```python
def _parse_ods(filepath: Path) -> str:
    """
    Parse an ODS spreadsheet to a Markdown table.

    Uses the odf engine via pandas. Same behavior as _parse_excel but
    for OpenDocument Spreadsheet format.

    Args:
        filepath: Path to the .ods file.

    Returns:
        Markdown table string. Empty string "" if the DataFrame has 0 rows.
    """
```

**Implementation**: Identical logic to `_parse_excel` but with `engine="odf"`. Factoring the shared pandas-to-markdown logic into a helper is tempting but premature -- the functions are 5 lines each, and engine selection differs. Keep them separate for clarity.

---

### _parse_pdf()

```python
def _parse_pdf(filepath: Path) -> str:
    """
    Parse a PDF file to Markdown.

    Attempts native text extraction via docling first. If the extracted text
    density is below the scanned threshold (< 50 chars/page average), or if
    docling raises any exception, falls back to Gemini Vision via _parse_image().

    If docling is not installed (ImportError at module load), ALL PDFs route
    directly to _parse_image().

    Args:
        filepath: Path to the PDF file.

    Returns:
        Markdown string from either docling or Gemini Vision.

    Side effects:
        - If docling path: reads file (read-only).
        - If Vision fallback: uploads to Gemini, deletes after.
    """
```

**Implementation sketch**:

```python
def _parse_pdf(filepath: Path) -> str:
    if not DOCLING_AVAILABLE:
        logger.warning("docling not available, routing PDF to Gemini Vision: %s", filepath.name)
        return _parse_image(filepath)

    try:
        # docling extraction (exact API TBD based on docling version)
        result = _docling_convert(filepath)
        text = result.document.export_to_markdown()
        page_count = result.document.num_pages()

        if _is_scanned_pdf(text, page_count):
            logger.info("PDF classified as scanned (low text density), falling back to Vision: %s", filepath.name)
            return _parse_image(filepath)

        return text
    except Exception as exc:
        logger.warning("docling failed for %s, falling back to Vision: %s", filepath.name, exc)
        return _parse_image(filepath)
```

**Design decision on docling API**: The exact docling API calls depend on the installed version. The design encapsulates docling interaction in a private `_docling_convert()` function that returns a result object. This isolates the docling version-specific API from the classification logic, making it easy to swap docling for PyMuPDF later without touching the fallback flow.

```python
def _docling_convert(filepath: Path):
    """Encapsulate docling API. Returns a conversion result with .document attribute."""
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    return converter.convert(str(filepath))
```

---

### _parse_image()

```python
def _parse_image(filepath: Path) -> str:
    """
    Parse an image or scanned document via Gemini Vision.

    Uploads the file to Gemini's file store, sends it with a text extraction
    prompt, and returns the extracted text. The uploaded file is always deleted
    from Gemini storage in a finally block.

    Retries once on any exception during extraction (total: 2 attempts).

    Args:
        filepath: Path to the image/document file.

    Returns:
        Extracted text as a string.

    Raises:
        Exception: If both attempts fail. The last exception propagates.

    Side effects:
        - Uploads file to Gemini storage (genai.upload_file).
        - Deletes file from Gemini storage (genai.delete_file) in finally.
        - Makes a Gemini API call (MODEL.generate_content).

    Guarantees:
        - genai.delete_file() is ALWAYS called if upload succeeded, even on error.
    """
```

**Implementation sketch**:

```python
_VISION_PROMPT = (
    "Extract all text from this document. "
    "Preserve table structure as Markdown tables. "
    "Return only the extracted text with no additional commentary."
)

def _parse_image(filepath: Path) -> str:
    last_exception = None
    for attempt in range(2):  # 2 total attempts
        uploaded_file = None
        try:
            uploaded_file = genai.upload_file(str(filepath))
            response = MODEL.generate_content([_VISION_PROMPT, uploaded_file])
            return response.text.strip()
        except Exception as exc:
            last_exception = exc
            if attempt == 0:
                logger.warning("Vision extraction failed (attempt 1), retrying: %s", exc)
        finally:
            if uploaded_file is not None:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception as cleanup_exc:
                    logger.warning("Failed to delete Gemini file %s: %s", uploaded_file.name, cleanup_exc)
    raise last_exception
```

**Design decision -- retry scope**: The retry wraps BOTH upload and extraction. If the upload fails, we retry the whole operation. If only extraction fails, we also re-upload (simpler, avoids reusing a possibly-corrupted file reference). The `finally` block runs on EACH attempt, so files are cleaned up per-attempt, not accumulated.

**Design decision -- cleanup failure**: If `genai.delete_file()` raises, we log a WARNING but do NOT suppress the main exception. Orphaned files in Gemini storage are a minor resource leak, not a correctness issue.

---

### _parse_html()

```python
def _parse_html(filepath: Path) -> str:
    """
    Parse an HTML file to clean text or Markdown.

    Attempts docling HTML-to-Markdown first. If docling fails (not installed
    or raises), falls back to BeautifulSoup4: extracts text, strips whitespace
    per line, collapses consecutive blank lines.

    Args:
        filepath: Path to the .html/.htm file.

    Returns:
        Clean text string (no HTML tags).

    Side effects:
        Reads file from disk. Encoding errors handled with 'replace' mode.
    """
```

**Implementation sketch**:

```python
def _parse_html(filepath: Path) -> str:
    if DOCLING_AVAILABLE:
        try:
            result = _docling_convert(filepath)
            return result.document.export_to_markdown()
        except Exception as exc:
            logger.warning("docling HTML conversion failed for %s, using BS4: %s", filepath.name, exc)

    # BeautifulSoup4 fallback
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_html = f.read()

    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n")
    # Strip per line, collapse blank lines
    lines = [line.strip() for line in text.splitlines()]
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()
```

**Design decision -- encoding**: The `errors="replace"` mode prevents `UnicodeDecodeError` for malformed HTML files. Lost characters are logged implicitly (the replacement character appears in output). This matches the current behavior in `robot_comparativas.py` line 74.

---

### _is_scanned_pdf()

```python
def _is_scanned_pdf(text: str, page_count: int, threshold: int = 50) -> bool:
    """
    Heuristic to classify a PDF as scanned based on text density.

    Args:
        text: Extracted text from docling.
        page_count: Number of pages in the PDF.
        threshold: Minimum average characters per page to be considered native.

    Returns:
        True if the PDF is likely scanned (below threshold), False otherwise.
    """
    avg_chars = len(text) / max(1, page_count)
    return avg_chars < threshold
```

---

### _detectar_proveedores()

```python
def _detectar_proveedores(markdown: str, filepath: Path) -> list[str]:
    """
    Step 1: Detect all providers in a comparatives document.

    Sends the Markdown to Gemini with a JSON-response prompt. Parses the
    JSON response to extract the provider list.

    Args:
        markdown: Full document content as Markdown.
        filepath: Original file path (used in error messages only).

    Returns:
        List of provider name strings.

    Raises:
        NoProvidersDetectedError: If the JSON response has an empty providers list.
        json.JSONDecodeError: If Gemini returns unparseable JSON after all retries.
    """
```

**Prompt design (exact text)**:

```python
_PROMPT_DETECT_PROVIDERS = """Analyze this price comparison document and identify ALL providers/suppliers.

Return ONLY a valid JSON object with no additional text.
If no providers are found, return {"proveedores": []}.

JSON format:
{
  "proveedores": ["Provider Name 1", "Provider Name 2"]
}

Important:
- Include the FULL provider name as it appears in the document.
- Do NOT include the client/hospital name as a provider.
- Do NOT include column headers, item descriptions, or other non-provider text.
"""
```

**Implementation sketch**:

```python
def _detectar_proveedores(markdown: str, filepath: Path) -> list[str]:
    data = _llamar_gemini_json(_PROMPT_DETECT_PROVIDERS, markdown)
    providers = data.get("proveedores", [])

    if not providers:
        raise NoProvidersDetectedError(filepath)

    logger.info("Detected %d providers in %s: %s", len(providers), filepath.name, providers)
    return providers
```

---

### _extraer_datos_proveedor()

```python
def _extraer_datos_proveedor(markdown: str, proveedor: str) -> dict:
    """
    Step 2: Extract data for a single provider from the comparatives document.

    Sends the Markdown with a provider-specific prompt to Gemini.
    Returns the structured dict with provider name and line items.

    Args:
        markdown: Full document content as Markdown.
        proveedor: Name of the provider to extract data for.

    Returns:
        Dict with keys "proveedor" (str) and "renglones" (list[dict]).
        Each renglon dict has: renglon, descripcion, marca, precio.

    Raises:
        json.JSONDecodeError: If Gemini returns unparseable JSON after all retries.
    """
```

**Prompt design (exact text)**:

```python
_PROMPT_EXTRACT_PROVIDER = """Extract ONLY the data for provider: {provider_name}

Analyze this price comparison document and return the items quoted by this specific provider.

Return ONLY a valid JSON object with no additional text.

JSON format:
{{
  "proveedor": "{provider_name}",
  "renglones": [
    {{
      "renglon": 1,
      "descripcion": "item description",
      "marca": "brand name or empty string",
      "precio": "numeric price as string, or empty string if not quoted"
    }}
  ]
}}

Rules:
- Include ALL items for this provider, even if the price is "no cotiza" or empty.
- "marca" must be a string (never null). Use empty string "" if unknown.
- "precio" must be a string. Keep the original value (cleaning happens later).
- "renglon" is the item number as it appears in the document.
- If no items found for this provider, return {{"proveedor": "{provider_name}", "renglones": []}}.
"""
```

**Implementation sketch**:

```python
def _extraer_datos_proveedor(markdown: str, proveedor: str) -> dict:
    prompt = _PROMPT_EXTRACT_PROVIDER.format(provider_name=proveedor)
    data = _llamar_gemini_json(prompt, markdown)
    logger.info("Extracted %d items for provider '%s'", len(data.get("renglones", [])), proveedor)
    return data
```

**Design decision -- prompt double braces**: The prompt template uses Python's `str.format()`, so literal braces in the JSON example must be doubled (`{{` and `}}`). The `{provider_name}` placeholder is the only substitution.

---

### _llamar_gemini_json()

```python
def _llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict:
    """
    Call Gemini expecting a JSON response. Retry on parse failure.

    Strips Markdown code fences from the response before JSON parsing.
    Retries up to max_retries times on json.JSONDecodeError.
    Does NOT retry on Gemini API errors (those fail fast).

    Args:
        prompt: The system/task prompt text.
        markdown: The document content to include after the prompt.
        max_retries: Number of additional attempts after the first failure.

    Returns:
        Parsed dict from the JSON response.

    Raises:
        json.JSONDecodeError: If all attempts return unparseable JSON.
        Any Gemini SDK exception: Propagated immediately (no retry).
    """
```

**Implementation** (refined from proposal):

```python
_CODE_FENCE_START = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)
_CODE_FENCE_END = re.compile(r"\n?\s*```\s*$", re.MULTILINE)

def _llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict:
    for attempt in range(max_retries + 1):
        # Gemini API call -- NOT retried on API errors
        response = MODEL.generate_content(prompt + "\n\n" + markdown)
        text = response.text.strip()

        # Strip code fences
        text = _CODE_FENCE_START.sub("", text)
        text = _CODE_FENCE_END.sub("", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt < max_retries:
                logger.warning("JSON parse failed (attempt %d), retrying...", attempt + 1)
            else:
                logger.error(
                    "Failed to parse JSON after %d attempts: %s",
                    max_retries + 1,
                    text[:200],
                )
                raise
```

**Design decision -- regex vs string replace**: The spec says "MUST use `re.sub`" for code fence stripping. We use compiled regex patterns for two reasons: (1) correctness (handles `json` language tag, optional newlines, multiline responses), (2) performance (compiled once at module load, reused across calls). Simple `.replace("```json", "")` would miss edge cases like trailing whitespace after fences.

**Design decision -- no retry on API errors**: The Gemini SDK raises specific exceptions for rate limiting (429), network errors, etc. These are NOT `json.JSONDecodeError`, so the `except json.JSONDecodeError` block does not catch them. They propagate immediately. This is intentional: retrying API errors without backoff would likely fail again and waste latency. Rate limit retry with exponential backoff is a future enhancement.

---

### _limpiar_precio()

```python
def _limpiar_precio(raw: str) -> str:
    """
    Clean a raw price string to a normalized numeric format.

    Handles Argentine (1.234,56), US (1,234.56), and comma-decimal (12,34)
    formats. Strips currency symbols and whitespace.

    Args:
        raw: Raw price string from Gemini extraction.

    Returns:
        Formatted price as "1234.56" (two decimals, dot separator),
        or empty string "" if unparseable or non-cotizable.

    Side effects:
        Logs a WARNING for unparseable non-empty price strings.
    """
```

**Implementation** (refined from proposal):

```python
_NON_COTIZABLE = {"", "-", "n/a", "no cotiza", "sin precio", "s/p"}

def _limpiar_precio(raw: str) -> str:
    if raw is None:
        return ""

    stripped = str(raw).strip()
    if stripped.lower() in _NON_COTIZABLE:
        return ""

    # Strip currency symbols and whitespace
    cleaned = re.sub(r"[$\u20ac]", "", stripped)  # $ and Euro sign
    cleaned = re.sub(r"\b(USD|ARS|EUR)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Determine format and normalize
    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_comma and has_dot:
        # Determine which is the decimal separator by position
        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_comma > last_dot:
            # Argentine: 1.234,56 -> dot is thousands, comma is decimal
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56 -> comma is thousands, dot is decimal
            cleaned = cleaned.replace(",", "")
    elif has_comma and not has_dot:
        # Comma-only decimal: 12,34 -> 12.34
        cleaned = cleaned.replace(",", ".")
    # else: dot-only or no separator -> already correct

    try:
        value = float(cleaned)
        return f"{value:.2f}"
    except ValueError:
        logger.warning("Non-numeric price, leaving empty: '%s'", raw)
        return ""
```

**Design decision -- set lookup for non-cotizable**: Using a frozen set with lowercase values for O(1) lookup. The `stripped.lower()` normalization handles case variations ("No cotiza", "NO COTIZA", "n/a", "N/A") without listing every case.

**Design decision -- EUR currency**: The spec mentions `"EUR"` and `"euro"` symbols. We handle both the Euro sign (`U+20AC`) and the string "EUR" via regex.

---

### _ensamblar_csv()

```python
def _ensamblar_csv(providers_data: list[dict], cliente: str) -> list[dict]:
    """
    Assemble the final CSV rows from per-provider extraction results.

    Merges all provider results, adds the cliente field, cleans prices,
    and re-numbers renglones if needed.

    Args:
        providers_data: List of dicts from Step 2 (each has "proveedor" and "renglones").
        cliente: Client name from obtener_cliente().

    Returns:
        List of dicts, each representing one CSV row with keys:
        renglon, descripcion, proveedor, marca, precio, cliente.

    Guarantees:
        - All prices are cleaned via _limpiar_precio().
        - Fully empty rows (no descripcion, no marca, no precio) are excluded.
        - Renglones are renumbered sequentially if values are missing/invalid.
        - Semicolons in descripcion/proveedor/marca are replaced with spaces.
    """
```

**Implementation sketch**:

```python
def _ensamblar_csv(providers_data: list[dict], cliente: str) -> list[dict]:
    rows = []
    for provider_result in providers_data:
        proveedor = provider_result.get("proveedor", "")
        renglones = provider_result.get("renglones", [])

        for renglon in renglones:
            descripcion = str(renglon.get("descripcion", "")).replace(";", " ")
            marca = str(renglon.get("marca", "") or "").replace(";", " ")
            precio_raw = str(renglon.get("precio", "") or "")
            precio = _limpiar_precio(precio_raw)

            # Skip fully empty rows
            if not descripcion.strip() and not marca.strip() and not precio:
                continue

            renglon_num = renglon.get("renglon", "")
            try:
                renglon_int = int(renglon_num)
                if renglon_int <= 0:
                    renglon_int = None
            except (ValueError, TypeError):
                renglon_int = None

            rows.append({
                "renglon": renglon_int,  # May be None; renumbered below
                "descripcion": descripcion.strip(),
                "proveedor": proveedor.replace(";", " "),
                "marca": marca.strip(),
                "precio": precio,
                "cliente": cliente,
            })

    # Renumber missing renglones sequentially
    counter = 1
    for row in rows:
        if row["renglon"] is None:
            row["renglon"] = counter
            counter += 1
        else:
            counter = row["renglon"] + 1

    return rows
```

**Design decision -- renumbering strategy**: When renglon values are missing or invalid, we assign sequential numbers starting from 1. If some renglones have valid values and others don't, we continue the sequence from the last valid value. This preserves document ordering while filling gaps.

**Design decision -- semicolons in text fields**: The CSV uses `;` as delimiter with no quoting. If a description contains a semicolon, it would break parsing. We replace semicolons with spaces in all text fields. This is a lossy transformation but necessary for the current output format.

**Design decision -- dicts over dataclass**: The spec question "dicts or dataclass?" is resolved as dicts. The data is tabular, short-lived (created in assembly, consumed in CSV write), and the fields are known. A dataclass adds no value here -- no methods, no validation beyond what assembly already does. Dicts are simpler and directly serializable to CSV.

---

### procesar_comparativa() (orchestration)

```python
def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
) -> Path:
    """
    Process a price comparison document through the two-step extraction pipeline.

    1. Parse the document to Markdown (via parsers.parse_document)
    2. Detect providers (Gemini Step 1)
    3. Extract data per provider (Gemini Step 2, sequential loop)
    4. Assemble rows and write CSV
    5. Move source file to Procesados/

    Args:
        ruta_archivo: Path to the uploaded file (in tmp/).
        nombre_original: Original filename (for client extraction and extension).

    Returns:
        Path to the generated CSV file.

    Raises:
        NoProvidersDetectedError: If no providers detected.
        ParserError: If document parsing fails.
        json.JSONDecodeError: If Step 1 JSON is unparseable after retries.
        Any Gemini SDK exception: If the API call itself fails.
    """
```

**Implementation sketch**:

```python
def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
) -> Path:
    if nombre_original:
        nombre_base = Path(nombre_original).stem
        extension = Path(nombre_original).suffix.lower()
    else:
        nombre_base = ruta_archivo.stem
        extension = ruta_archivo.suffix.lower()

    cliente = obtener_cliente(nombre_base)

    # Stage 1: Parse
    logger.info("Parsing document: %s", ruta_archivo.name)
    markdown = parse_document(ruta_archivo)

    # Stage 2: Detect providers
    logger.info("Step 1: Detecting providers in %s", ruta_archivo.name)
    providers = _detectar_proveedores(markdown, ruta_archivo)

    # Stage 3: Extract per provider
    all_provider_data = []
    for proveedor in providers:
        logger.info("Step 2: Extracting data for provider '%s'", proveedor)
        try:
            data = _extraer_datos_proveedor(markdown, proveedor)
            all_provider_data.append(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.error(
                "Failed to extract data for provider '%s', skipping: %s",
                proveedor, exc,
            )
            continue

    # Stage 4: Assemble CSV
    rows = _ensamblar_csv(all_provider_data, cliente)

    # Stage 5: Write CSV
    output_dir = get_output_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=cliente)
    processed_dir = get_processed_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=cliente)

    nombre_csv = nombre_unico(nombre_base, output_dir, ".csv")
    ruta_salida = output_dir / nombre_csv

    _write_csv(ruta_salida, rows)

    # Stage 6: Move source to Procesados
    nombre_proc = nombre_unico(nombre_base, processed_dir, extension)
    shutil.move(str(ruta_archivo), str(processed_dir / nombre_proc))

    logger.info("Comparativa processed: %s -> %s", ruta_archivo.name, ruta_salida.name)
    return ruta_salida
```

**CSV writing helper**:

```python
_CSV_COLUMNS = ["renglon", "descripcion", "proveedor", "marca", "precio", "cliente"]

def _write_csv(filepath: Path, rows: list[dict]) -> None:
    """Write assembled rows to a semicolon-delimited CSV file."""
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS, delimiter=";",
                                quoting=csv.QUOTE_NONE, escapechar=None)
        writer.writeheader()
        writer.writerows(rows)
```

**Design decision -- csv module vs manual string**: The current code writes raw text strings. The new implementation uses Python's `csv.DictWriter` with `QUOTE_NONE`. This is more robust against edge cases (embedded newlines, empty fields) while preserving the "no quoting" requirement from the spec. The `newline=""` parameter ensures the csv module controls line endings (as per Python docs), producing `\n` on all platforms.

---

## Error Handling

### Exception Hierarchy

```
ValueError
  +-- UnsupportedFormatError      (parsers.py)
  +-- NoProvidersDetectedError    (robot_comparativas.py)

RuntimeError
  +-- ParserError                 (parsers.py)
```

**Design decision**: No common `ParserBaseError`. The spec explicitly defines `UnsupportedFormatError` inheriting from `ValueError` and `ParserError` from `RuntimeError`. These are semantically different: `UnsupportedFormatError` is a client error (wrong file type), while `ParserError` is a system error (parser infrastructure failed). A shared base class would conflate these categories. Keeping them separate allows `main.py` to differentiate if needed in the future (e.g., return 400 for ValueError, 500 for RuntimeError).

### Error Matrix

| Error | Where raised | Where caught | Action | HTTP result |
|-------|-------------|--------------|--------|-------------|
| `UnsupportedFormatError` | `parse_document()` | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `ParserError` | `parse_document()` (wrapping internal) | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `NoProvidersDetectedError` | `_detectar_proveedores()` | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `json.JSONDecodeError` (Step 1) | `_llamar_gemini_json()` | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `json.JSONDecodeError` (Step 2) | `_llamar_gemini_json()` | `procesar_comparativa()` loop | Log ERROR, skip provider, continue | Success (partial CSV) |
| `genai.APIError` / SDK errors | Gemini SDK | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `FileNotFoundError` (temp) | `parse_document()` | `main.py except` | Log traceback, return error template | 200 (error in UI) |
| `UnicodeDecodeError` (HTML) | `open()` | `_parse_html()` | `errors="replace"` mode, no exception | Lossy markdown (success path) |
| Cleanup failure (`genai.delete_file`) | `genai` SDK | `_parse_image() finally` | Log WARNING, do NOT suppress main exception | No effect on result |

### Logging Strategy

| Level | What gets logged | Example |
|-------|-----------------|---------|
| `INFO` | Normal pipeline progress: parse start, providers detected, per-provider extraction start/count, CSV written, file moved | `"Detected 3 providers in HOSPITAL_comp.xlsx: ['A', 'B', 'C']"` |
| `WARNING` | Recoverable issues: docling fallback to Vision, JSON retry, non-numeric price, Gemini file cleanup failure, docling import failure | `"JSON parse failed (attempt 1), retrying..."` |
| `ERROR` | Failed provider extraction (skipped), all JSON retries exhausted | `"Failed to extract data for provider 'X', skipping: ..."` |
| `EXCEPTION` | Unhandled errors caught by main.py (includes full traceback) | `"Error procesando archivo"` (via `logger.exception()`) |

**Design decision -- step numbers in logs**: Yes. Log messages for the two-step pipeline include `"Step 1:"` and `"Step 2:"` prefixes. This makes it trivial to grep logs for a specific step's behavior. Example: `"Step 1: Detecting providers in HOSPITAL_comp.xlsx"`, `"Step 2: Extracting data for provider 'Drogueria del Sud'"`.

**Design decision -- traceback in logs**: `logger.exception()` in `main.py` automatically includes the full traceback. `logger.error()` and `logger.warning()` do NOT include traceback (they log the exception message only). This is intentional: tracebacks for warnings (like a single provider failure) would be noise; tracebacks for unhandled top-level errors are essential for debugging.

---

## Gemini Integration

### Step 1: Detect Providers

**Prompt** (see `_PROMPT_DETECT_PROVIDERS` above in function interfaces section).

**Call pattern**:

```python
data = _llamar_gemini_json(_PROMPT_DETECT_PROVIDERS, markdown)
# data = {"proveedores": ["Drogueria del Sud", "Farmacia Central", ...]}
providers = data.get("proveedores", [])
```

**Expected output JSON schema**:

```json
{
  "proveedores": ["string", "..."]
}
```

- Exactly one key: `"proveedores"`.
- Value is an array of strings.
- Empty array is valid JSON but triggers `NoProvidersDetectedError`.

### Step 2: Extract Per Provider

**Prompt** (see `_PROMPT_EXTRACT_PROVIDER` above in function interfaces section).

**Call pattern**:

```python
prompt = _PROMPT_EXTRACT_PROVIDER.format(provider_name=proveedor)
data = _llamar_gemini_json(prompt, markdown)
# data = {"proveedor": "Drogueria del Sud", "renglones": [...]}
```

**Expected output JSON schema**:

```json
{
  "proveedor": "string",
  "renglones": [
    {
      "renglon": "integer or string",
      "descripcion": "string",
      "marca": "string (never null, empty string if unknown)",
      "precio": "string (raw, cleaned later)"
    }
  ]
}
```

### Gemini Vision Prompt (PDF/Image text extraction)

**Prompt** (exact text, defined in spec):

```
Extract all text from this document. Preserve table structure as Markdown tables. Return only the extracted text with no additional commentary.
```

**Call pattern**:

```python
uploaded_file = genai.upload_file(str(filepath))
response = MODEL.generate_content([_VISION_PROMPT, uploaded_file])
text = response.text.strip()
```

This is a TEXT EXTRACTION prompt, not a data extraction prompt. The goal is format normalization: convert an image/scanned document into readable Markdown that the Step 1/Step 2 prompts can consume.

---

## Resource Cleanup & Safety

### Cleanup Matrix

| Resource | Owner | When cleaned | How | Failure mode |
|----------|-------|-------------|-----|-------------|
| Temp file (`destino`) | `main.py` finally block | After processing (success or error) | `destino.unlink(missing_ok=True)` | If file was moved by robot: `missing_ok=True` handles it. If process crashes: file persists in tmp/ (manual cleanup). |
| Gemini uploaded file | `_parse_image()` finally block | After each Vision attempt | `genai.delete_file(uploaded_file.name)` | If delete fails: log WARNING, do not suppress main exception. File auto-expires in Gemini storage (48h TTL). |
| CSV output file | `procesar_comparativa()` | Created on success only | Written to `output_dir` | If writing fails: exception propagates, no partial CSV left (DictWriter writes atomically to a new file). |
| Source file in Procesados | `procesar_comparativa()` | On success (after CSV written) | `shutil.move()` | If move fails: exception propagates. CSV is already written. Main.py's finally block does NOT delete the source (it's in Procesados, not tmp). |

### Exception Safety Guarantees

1. **If `parse_document()` fails**: No CSV created. Temp file cleaned by `main.py` finally. No Gemini files leaked (Vision path has its own finally).

2. **If Step 1 fails (no providers or JSON error)**: No CSV created. Temp file cleaned by `main.py` finally.

3. **If Step 2 fails for one provider**: That provider's data is absent from CSV. Other providers' data is included. CSV is written. Source file is moved. This is a PARTIAL SUCCESS, not an error.

4. **If Step 2 fails for ALL providers**: `all_provider_data` is empty. `_ensamblar_csv()` returns empty list. CSV is written with header only. Source file is moved. This is technically a success (valid CSV, no error), but the CSV has no data rows. A future enhancement could detect this case and raise.

5. **If CSV write fails**: Exception propagates to `main.py`. Temp file cleaned by finally. No partial CSV (file was not yet closed/flushed).

6. **If `shutil.move()` fails**: Exception propagates to `main.py`. CSV IS already on disk (written before move). Temp file is NOT cleaned (it's at the original path, not in tmp -- actually it IS in tmp, so `main.py` finally deletes it). This means both the CSV and the source file might not be in the right place. Acceptable edge case for this iteration.

---

## Testing Architecture

### Test File Structure

```
tests/
  __init__.py          (empty, package marker)
  conftest.py          (shared fixtures)
  fixtures/            (test data directory)
    sample.html        (small HTML file with a table)
  test_parsers.py      (9 tests)
  test_robot_comparativas.py  (9 tests)
```

### Fixture Design (`tests/conftest.py`)

```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_gemini_model(mocker):
    """Patch MODEL.generate_content to return controlled responses."""
    mock = mocker.patch("app.config.MODEL.generate_content")
    return mock

@pytest.fixture
def mock_genai_upload(mocker):
    """Patch genai.upload_file to return a mock with .name attribute."""
    mock_file = MagicMock()
    mock_file.name = "test-uploaded-file-id"
    mock = mocker.patch("google.generativeai.upload_file", return_value=mock_file)
    return mock

@pytest.fixture
def mock_genai_delete(mocker):
    """Patch genai.delete_file to do nothing."""
    mock = mocker.patch("google.generativeai.delete_file")
    return mock

@pytest.fixture
def sample_xlsx(tmp_path):
    """Create a minimal .xlsx file with 3 columns and 5 rows."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Item", "Description", "Price"])
    for i in range(1, 6):
        ws.append([i, f"Product {i}", f"{i * 100}.00"])
    path = tmp_path / "test.xlsx"
    wb.save(path)
    return path

@pytest.fixture
def sample_xls(tmp_path):
    """Create a minimal .xls file using pandas + xlrd-compatible write."""
    import pandas as pd
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    path = tmp_path / "test.xls"
    df.to_excel(path, index=False, engine="xlwt")
    return path

@pytest.fixture
def sample_ods(tmp_path):
    """Create a minimal .ods file using pandas."""
    import pandas as pd
    df = pd.DataFrame({"Col1": [10, 20], "Col2": ["a", "b"]})
    path = tmp_path / "test.ods"
    df.to_excel(path, index=False, engine="odf")
    return path

@pytest.fixture
def sample_html(tmp_path):
    """Create a minimal HTML file with a table."""
    content = """<html><body>
    <h1>Test Document</h1>
    <table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>
    </body></html>"""
    path = tmp_path / "test.html"
    path.write_text(content, encoding="utf-8")
    return path

def gemini_response(text: str) -> MagicMock:
    """Helper to create a mock Gemini response with .text attribute."""
    resp = MagicMock()
    resp.text = text
    return resp
```

### Mock Strategy

| What | How mocked | Why |
|------|-----------|-----|
| `MODEL.generate_content` | `mocker.patch("app.config.MODEL.generate_content")` | All Gemini calls go through the shared MODEL instance |
| `genai.upload_file` | `mocker.patch("google.generativeai.upload_file")` | Vision uploads |
| `genai.delete_file` | `mocker.patch("google.generativeai.delete_file")` | Vision cleanup verification |
| docling | `mocker.patch("app.parsers._docling_convert")` | PDF/HTML native extraction |
| `DOCLING_AVAILABLE` flag | `mocker.patch("app.parsers.DOCLING_AVAILABLE", False)` | Test docling-unavailable path |

**Design decision -- real files vs generated**: Excel (`.xlsx`) and ODS (`.ods`) files are GENERATED on the fly using `openpyxl` and `pandas` respectively within conftest fixtures. This avoids committing binary files to the repo and makes tests self-documenting (the fixture shows exactly what data the test operates on). HTML fixtures are raw strings written to tmp_path. PDF fixtures are NOT real PDF files -- docling is mocked, so we only need a file that exists on disk with a `.pdf` extension.

**Design decision -- no `.xls` generation in tests**: The `xlwt` package (needed to WRITE `.xls`) may not be in requirements. For `test_parse_excel_xls`, we can either: (a) add `xlwt` as a test dependency, or (b) create a minimal `.xls` binary in the fixture. Option (a) is cleaner. Add `xlwt` to test requirements only (not production requirements).

### Test Catalog

**tests/test_parsers.py** (9 tests):

| Test | Fixture | Mocks | Assertion |
|------|---------|-------|-----------|
| `test_parse_excel_xlsx` | `sample_xlsx` | None | Result contains `\|` (pipe), all 5 data rows present, no "nan" |
| `test_parse_excel_xls` | `sample_xls` | None | Result is non-empty Markdown table |
| `test_parse_ods` | `sample_ods` | None | Result is non-empty Markdown table |
| `test_parse_html` | `sample_html` | None (or mock docling) | No HTML tags in output, "Test Document" and table data present |
| `test_parse_pdf_native` | tmp `.pdf` | Mock `_docling_convert` (returns rich text), mock `genai.upload_file` | `genai.upload_file` NOT called |
| `test_parse_pdf_scanned_fallback` | tmp `.pdf` | Mock `_docling_convert` (returns sparse text), mock Vision | `genai.upload_file` called exactly once |
| `test_parse_image_formats` | tmp `.jpg`, `.png`, `.tiff` | Mock Vision | `genai.upload_file` called, text returned |
| `test_unsupported_format` | tmp `.zip` | None | `UnsupportedFormatError` raised, message contains ".zip" |
| `test_gemini_vision_cleanup` | tmp `.png` | Mock upload (success), mock generate_content (raises) | `genai.delete_file` called exactly once |

**tests/test_robot_comparativas.py** (9 tests):

| Test | Mocks | Assertion |
|------|-------|-----------|
| `test_detect_providers` | Gemini returns `{"proveedores": ["A", "B"]}` | Returns `["A", "B"]` |
| `test_extract_per_provider` | Gemini returns valid Step 2 JSON | Returns dict with `renglones` list |
| `test_assembly_adds_fields` | None (pure Python) | Every row has `proveedor` and `cliente` keys |
| `test_price_cleaning` | None | `"$1.234,56"` -> `"1234.56"`, `"1,234.56"` -> `"1234.56"`, `"12,34"` -> `"12.34"` |
| `test_price_cleaning_invalid` | None | `"no cotiza"` -> `""`, `"consultar"` -> `""` with WARNING logged |
| `test_retry_on_invalid_json` | Gemini: 1st call bad JSON, 2nd call good JSON | Result is good dict, 2 total Gemini calls |
| `test_no_providers_raises` | Gemini returns `{"proveedores": []}` | `NoProvidersDetectedError` raised |
| `test_cliente_from_filename` | None | `obtener_cliente("HOSPITAL_ITALIANO_2024")` returns `"HOSPITAL"` |
| `test_csv_output_format` | Full pipeline mock (parse_document, Gemini) | CSV header = `renglon;descripcion;proveedor;marca;precio;cliente`, UTF-8, no BOM |

---

## Dependencies & Imports

### Import Graph (no cycles)

```
app/config.py           (no app imports)
     ^
     |
app/robot.py            (imports config)
     ^
     |
app/parsers.py          (imports config)
     ^
     |
app/robot_comparativas.py  (imports parsers, config, robot)
     ^
     |
app/main.py             (imports robot_comparativas, robot, config)
```

No circular dependencies. `parsers.py` depends only on `config.py` (for `MODEL`). `robot_comparativas.py` depends on `parsers.py` (for `parse_document`) and `robot.py` (for `obtener_cliente`, `nombre_unico`). `main.py` sits at the top.

### Exact Import Blocks

**app/parsers.py**:

```python
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
import google.generativeai as genai

from app.config import MODEL

logger = logging.getLogger(__name__)

# Guarded docling import
try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.warning(
        "docling not available. All PDFs will be processed via Gemini Vision. "
        "Install docling for native PDF text extraction."
    )
```

**app/robot_comparativas.py**:

```python
import csv
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from app.config import MODEL, get_output_dir, get_processed_dir, COMPARATIVAS_OUTPUT_BASE
from app.parsers import parse_document
from app.robot import obtener_cliente, nombre_unico

logger = logging.getLogger(__name__)
```

**app/main.py** (additions only):

```python
import logging
# ... existing imports remain ...
logger = logging.getLogger(__name__)
```

### Docling Fallback Strategy

The guarded import at module load time is the ONLY check point. If `docling` is not installed:

1. `DOCLING_AVAILABLE` is `False`.
2. `_parse_pdf()` routes ALL PDFs to `_parse_image()` (Gemini Vision).
3. `_parse_html()` falls back to BeautifulSoup4.
4. No runtime errors. No user-visible impact beyond slightly different Markdown quality for native PDFs.
5. The WARNING log at import time is the only signal.

This means the application is fully functional without docling. Docling is an OPTIONAL enhancement for better PDF text extraction quality.

### New Dependencies for requirements.txt

| Package | Required for | Required/Optional |
|---------|-------------|-------------------|
| `docling` | PDF native extraction | Optional (app works without it) |
| `beautifulsoup4` | HTML fallback parsing | Required |
| `pytest` | Tests | Dev only |
| `pytest-mock` | Test mocking | Dev only |
| `tabulate` | `DataFrame.to_markdown()` dependency | Required (pandas uses it) |

**Note**: `pandas.DataFrame.to_markdown()` requires the `tabulate` package. It is NOT bundled with pandas. This must be added to `requirements.txt`. Without it, `to_markdown()` raises `ImportError`.

---

## Implementation Notes

### Non-Obvious Choices and Tradeoffs

1. **`tabulate` dependency**: The single biggest hidden requirement. `pandas.to_markdown()` delegates to `tabulate`. If `tabulate` is missing, the parser router fails on the FIRST Excel file. This must be added to requirements explicitly and tested.

2. **CSV writer with QUOTE_NONE**: Python's `csv.DictWriter` with `quoting=csv.QUOTE_NONE` will raise `csv.Error` if a field contains the delimiter (`;`) and no `escapechar` is set. The assembly function MUST strip semicolons from all text fields BEFORE passing to the writer. This is handled in `_ensamblar_csv()`.

3. **Vision retry re-uploads**: Each retry attempt in `_parse_image()` re-uploads the file. This means 2 uploads for 2 attempts. An alternative is to upload once and retry only `generate_content()`, but this risks using a stale file reference. The simpler "retry everything" approach is correct for this iteration.

4. **Step 2 exception catch breadth**: The per-provider loop catches `Exception` (not just `json.JSONDecodeError`). This is intentional: if Gemini returns an unexpected SDK error for one provider, the other providers should still be processed. However, if Gemini is DOWN (not just returning bad data), all providers will fail sequentially and we'll waste N API calls before reporting the error. This is acceptable for this iteration since N is typically 3-8.

5. **Renumbering logic**: The renumbering in `_ensamblar_csv()` continues the sequence from the last valid renglon value. This means if provider A has renglones [1, 2, 3] and provider B has [None, None], B's items become [4, 5]. This may or may not be desired. An alternative is to renumber WITHIN each provider (both A and B start from 1). The current approach (global sequence) preserves the document's item numbering across providers.

6. **No `csv.QUOTE_MINIMAL` or quoting**: The spec requires "no quoting of fields (current behavior, preserved)". This means `QUOTE_NONE` in the csv writer. Combined with semicolons being stripped from text fields, this is safe. But if a field contains a newline, the CSV will be malformed. Gemini is unlikely to return newlines in individual fields, but this is a known fragility.

7. **docling API instability**: docling's Python API may change between versions. The `_docling_convert()` wrapper function isolates version-specific API calls. If docling changes its API, only this one function needs updating.

### Assumptions

- The `genai.upload_file()` and `genai.delete_file()` APIs are synchronous and blocking.
- The `MODEL.generate_content()` call is synchronous (not async).
- `pandas.DataFrame.to_markdown()` produces pipe-delimited tables with a separator row.
- The `tabulate` package is available (must be added to requirements).
- Gemini's `upload_file` returns an object with a `.name` attribute usable in `delete_file`.
- The `csv` module's `DictWriter` respects the field order given in `fieldnames`.
