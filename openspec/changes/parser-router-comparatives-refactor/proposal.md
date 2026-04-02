# Proposal: Parser Router + Comparatives Refactoring

## Intent

The current codebase has two independent modules (`robot.py` and `robot_comparativas.py`) that each implement their own document parsing logic before sending content to Gemini. This creates several concrete problems:

1. **Duplicated parsing logic** -- Both modules independently handle Excel (`.xls`/`.xlsx`) with pandas, and both use `genai.upload_file()` as a catch-all for everything else. Adding a new format means touching two files with nearly identical code.

2. **No abstraction between "parse document" and "call AI"** -- Document format detection, reading, and conversion are tangled directly into the Gemini prompt-building logic. This makes it impossible to test parsing independently from AI extraction.

3. **Comparatives extraction accuracy** -- The current single-prompt approach asks Gemini to simultaneously detect providers, identify all item-provider combinations, normalize prices, and produce CSV. For documents with complex/varying layouts (vertical, horizontal, mixed), this is fragile. A two-step extraction (detect providers first, then extract per provider) gives Gemini a narrower, more reliable task at each step.

4. **Weak error handling** -- No retry on malformed Gemini responses, no cleanup of `genai.upload_file()` resources on failure, and non-numeric prices silently break downstream processing. The `except Exception` in `main.py` catches everything but logs nothing.

5. **No tests** -- Zero test coverage. No `tests/` directory exists. Any refactoring without tests is flying blind.

**Benefits of this change:**
- Single source of truth for document parsing (DRY)
- Gemini receives clean Markdown regardless of source format
- Two-step comparatives extraction is more accurate and debuggable
- Structured error handling with retries, logging, and cleanup
- Testable architecture with clear module boundaries

## Scope

### NEW modules
- **`app/parsers.py`** -- Parser router. Single entry point `parse_document(filepath: Path) -> str` that returns Markdown for any supported format.
- **`tests/test_parsers.py`** -- Unit tests for parser router with mocked dependencies.
- **`tests/test_robot_comparativas.py`** -- Unit tests for two-step comparatives extraction with mocked Gemini.
- **`tests/__init__.py`** -- Package init.
- **`tests/conftest.py`** -- Shared pytest fixtures.

### MODIFIED modules
- **`app/robot_comparativas.py`** -- Major refactor: replace single-prompt extraction with two-step process (detect providers, then extract per provider). Consume parsed Markdown from `parsers.py` instead of handling formats internally. Add retry logic, price cleaning, and structured JSON output.
- **`app/main.py`** -- Integrate parser router into the processing pipeline. Add logging. Improve error handling with `finally` block for temp file cleanup.
- **`requirements.txt`** -- Add `docling`, `beautifulsoup4`, `pytest`, `pytest-mock`.

### UNCHANGED modules
- **`app/robot.py`** -- Will NOT be modified in this change. It can adopt the parser router in a future iteration, keeping this change's blast radius contained.
- **`app/config.py`** -- No changes needed. Model configuration, paths, and directory helpers remain as-is.
- **`app/templates/`**, **`app/static/`** -- No frontend changes.
- **FastAPI endpoints** (`/procesar`, `/descargar`) -- Same interface, same routes. Internal implementation changes only.

### Dependencies to add
| Package | Purpose | Version constraint |
|---------|---------|-------------------|
| `docling` | PDF (native) and HTML to Markdown conversion | latest stable |
| `beautifulsoup4` | HTML fallback parser, text cleaning | `>=4.12` |
| `pytest` | Test runner | `>=8.0` |
| `pytest-mock` | Gemini mock fixtures | `>=3.12` |

### Dependencies already present (no changes)
- `pandas`, `openpyxl`, `xlrd`, `odfpy` -- Excel/ODS parsing
- `google-generativeai` -- Gemini API

## Approach

### Phase 1: Parser Router (`app/parsers.py`)

**Architecture:**

```
parse_document(filepath: Path) -> str
    |
    +-- route by extension
    |
    +-- .xlsx, .xls  -->  _parse_excel(filepath) --> Markdown table
    +-- .ods         -->  _parse_ods(filepath)   --> Markdown table
    +-- .pdf (native) -> _parse_pdf(filepath)    --> Markdown (via docling)
    +-- .pdf (scanned), .jpg, .png, .tiff --> _parse_image(filepath) --> Markdown (via Gemini Vision)
    +-- .html, .htm  --> _parse_html(filepath)   --> clean text (docling or BS4)
    +-- unsupported  --> raise UnsupportedFormatError
```

**Key design decisions:**

1. **PDF classification** -- `docling` attempts native text extraction first. If the extracted text is below a quality threshold (e.g., <50 characters per page on average), fall back to Gemini Vision for scanned/image-based PDFs. This avoids requiring the user to specify the PDF type.

2. **Excel to Markdown** -- Use pandas to read the spreadsheet with `header=None` (preserve raw structure), then convert to a Markdown table. This is critical: the current code in `robot_comparativas.py` converts to CSV with semicolons, which loses table structure context for the AI. Markdown tables preserve column alignment semantics.

3. **Gemini Vision for images** -- Upload via `genai.upload_file()`, prompt with "Extract all text from this document. Preserve table structure as Markdown tables." This is a TEXT EXTRACTION step, NOT a data extraction step. The AI extraction happens later in the robot modules.

4. **Resource cleanup** -- `_parse_image()` wraps `genai.upload_file()` in a try/finally to call `genai.delete_file()` after extraction, preventing orphaned files in the Gemini file store.

5. **Return type** -- Always `str` containing Markdown. No structured data at this layer. The parser's job is FORMAT NORMALIZATION, not DATA EXTRACTION.

**Error handling:**
- `UnsupportedFormatError(extension)` -- custom exception for unknown formats.
- `ParserError(filepath, cause)` -- wraps underlying exceptions (pandas read failures, docling errors, etc.) with the file path for debugging.
- Gemini Vision errors trigger a single retry before raising.

### Phase 2: Comparatives Refactoring (`app/robot_comparativas.py`)

**Two-step extraction design:**

```
procesar_comparativa(filepath, nombre_original)
    |
    1. markdown = parse_document(filepath)           # Phase 1 output
    2. cliente = obtener_cliente(nombre_base)
    |
    3. STEP 1: providers = _detectar_proveedores(markdown)
    |   Prompt: "Identify all providers in this document.
    |            Return ONLY JSON: {"proveedores": [...]}"
    |   Returns: list[str]
    |
    4. STEP 2: for provider in providers:
    |     data = _extraer_datos_proveedor(markdown, provider)
    |     Prompt: "Extract data ONLY for provider: {name}.
    |              Return JSON: {"proveedor": "{name}",
    |                            "renglones": [{"renglon": ...,
    |                                           "descripcion": ...,
    |                                           "marca": ...,
    |                                           "precio": ...}]}"
    |     Returns: dict with structured data
    |
    5. ASSEMBLY (pure Python, no AI):
    |   - Merge all provider results
    |   - Add "proveedor" field from each step 2 response
    |   - Add "cliente" field from filename
    |   - Clean prices: strip $, convert comma decimals, validate numeric
    |   - Number renglones if not explicit in document
    |
    6. Export CSV: renglon;descripcion;proveedor;marca;precio;cliente
```

**Data flow detail:**

```
Document  -->  [Parser Router]  -->  Markdown string
                                         |
                                    [Step 1: Detect]  -->  ["Proveedor A", "Proveedor B", ...]
                                         |
                                    [Step 2: Extract]  -->  per-provider JSON
                                         |              (runs N times, one per provider)
                                         |
                                    [Assembly]  -->  merged list of dicts
                                         |
                                    [CSV Export]  -->  output .csv file
```

**JSON parsing with retry:**

```python
def _llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict:
    """Call Gemini expecting JSON. Retry on parse failure."""
    for attempt in range(max_retries + 1):
        response = MODEL.generate_content(prompt + "\n\n" + markdown)
        text = response.text.strip()
        # Strip markdown code fences if present
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt == max_retries:
                logger.error(f"Failed to parse JSON after {max_retries + 1} attempts: {text[:200]}")
                raise
            logger.warning(f"JSON parse failed (attempt {attempt + 1}), retrying...")
    # unreachable, but makes type checker happy
    raise RuntimeError("Unreachable")
```

**Price cleaning:**

```python
def _limpiar_precio(raw: str) -> str:
    """Clean price string to numeric. Return empty string if unparseable."""
    if not raw or raw.strip() in ("", "-", "N/A", "n/a", "no cotiza"):
        return ""
    cleaned = re.sub(r'[$\s]', '', str(raw))
    # Handle comma as decimal separator (Argentine convention)
    if ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')
    elif ',' in cleaned and '.' in cleaned:
        # 1.234,56 format -> 1234.56
        cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        value = float(cleaned)
        return f"{value:.2f}"
    except ValueError:
        logger.warning(f"Non-numeric price, leaving empty: '{raw}'")
        return ""
```

**No providers detected:**

```python
if not providers:
    raise NoProvidersDetectedError(
        f"No providers detected in document '{filepath.name}'. "
        "The document may not be a valid price comparison, or the format is unrecognized."
    )
```

### Phase 3: Integration (`app/main.py`)

**Changes:**

1. **Import `parse_document`** from `app.parsers` instead of handling formats in each robot module.

2. **Processing pipeline for comparatives:**
   ```python
   # Before (current):
   csv_generado = procesar_comparativa(destino, nombre_original)

   # After:
   csv_generado = procesar_comparativa(destino, nombre_original)
   # (parser router is called internally by procesar_comparativa)
   ```
   The external call signature in `main.py` does NOT change. The parser router is consumed internally by `robot_comparativas.py`. This keeps the change contained.

3. **Add logging** -- Replace bare `except Exception` with structured logging using Python's `logging` module. Log the full traceback at ERROR level, return a user-friendly message to the template.

4. **Temp file cleanup** -- Add a `finally` block to delete the temp file in `get_tmp_dir()` after processing (success or failure), since the processed file is moved by the robot module on success.

### Phase 4: Testing Strategy

**Unit tests (`tests/test_parsers.py`):**

| Test | What it validates |
|------|------------------|
| `test_parse_excel_xlsx` | `.xlsx` file produces Markdown table with correct columns/rows |
| `test_parse_excel_xls` | `.xls` file (xlrd engine) produces Markdown |
| `test_parse_ods` | `.ods` file produces Markdown |
| `test_parse_html` | `.html` produces clean text without tags |
| `test_parse_pdf_native` | Native PDF extracted via docling (mock docling) |
| `test_parse_pdf_scanned_fallback` | Scanned PDF falls back to Gemini Vision (mock both) |
| `test_parse_image_formats` | `.jpg`, `.png`, `.tiff` routed to Gemini Vision (mock) |
| `test_unsupported_format` | `.zip` raises `UnsupportedFormatError` |
| `test_gemini_vision_cleanup` | `genai.delete_file()` called even on error |

**Unit tests (`tests/test_robot_comparativas.py`):**

| Test | What it validates |
|------|------------------|
| `test_detect_providers` | Step 1 correctly parses provider list from Gemini JSON |
| `test_extract_per_provider` | Step 2 correctly parses per-provider data |
| `test_assembly_adds_fields` | Assembly adds `proveedor` and `cliente` fields |
| `test_price_cleaning` | Various price formats cleaned correctly |
| `test_price_cleaning_invalid` | Non-numeric prices become empty string |
| `test_retry_on_invalid_json` | Retry logic triggers on `JSONDecodeError` |
| `test_no_providers_raises` | Empty provider list raises `NoProvidersDetectedError` |
| `test_cliente_from_filename` | `obtener_cliente()` extracts correctly from stem |
| `test_csv_output_format` | Final CSV has correct headers and delimiter |

**Mocking strategy:**
- `unittest.mock.patch` on `MODEL.generate_content` to return canned JSON responses.
- `unittest.mock.patch` on `genai.upload_file` and `genai.delete_file` for Vision tests.
- `pytest.tmp_path` for file system fixtures (create temp Excel/HTML files).
- NO integration tests with real Gemini in this phase. Those can be added later as a separate opt-in test suite with `@pytest.mark.integration`.

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Gemini Vision accuracy on scanned PDFs** | Low-quality text extraction degrades downstream extraction | Medium | PDF classification heuristic (text length threshold) ensures only truly scanned PDFs hit Vision. Can tune threshold. Fallback: user re-uploads as image. |
| **Two-step extraction adds latency** | 1 + N Gemini calls instead of 1 (where N = number of providers) | High | Acceptable tradeoff for accuracy. Typical N is 3-8 providers. Can parallelize Step 2 calls with `asyncio.gather()` in a future iteration. |
| **docling dependency complexity** | Large dependency tree, potential install issues on Windows | Medium | Pin docling version in requirements. If install fails, the PDF native parser gracefully falls back to Gemini Vision (same as scanned PDF path). Add a try/except import with a clear warning. |
| **Gemini returns invalid JSON despite retry** | Provider detection or data extraction fails completely | Low | After 2 retries, log the raw response and raise with context. The per-provider loop continues with remaining providers (one failure doesn't abort all). |
| **Breaking `robot.py` accidentally** | The main extraction module stops working | Low | `robot.py` is UNCHANGED in this proposal. It does not import or depend on `parsers.py`. Zero risk of regression. |
| **Markdown table formatting varies** | Pandas-generated Markdown might not match what Gemini expects | Low | Use pandas `.to_markdown()` which produces standard pipe-delimited tables. Gemini handles these well. Validate with integration tests. |
| **Price format edge cases** | Argentine/Latin American price formats (1.234,56) miscleaned | Medium | Explicit handling of comma-as-decimal and dot-as-thousands in `_limpiar_precio()`. Add test cases for all known formats. |

## Rollback Plan

This refactoring is designed for safe, incremental rollback:

1. **Immediate rollback** -- `git revert` the merge commit. Since `robot.py` is unchanged, the original extraction pipeline continues working for non-comparativas documents. The comparativas module reverts to its single-prompt approach.

2. **Partial rollback (keep parser, revert comparatives)** -- If only the two-step extraction is problematic:
   - Revert `robot_comparativas.py` to its pre-refactor state.
   - Keep `parsers.py` -- it has no external side effects and can be adopted incrementally.
   - `main.py` changes are minimal and can be reverted independently.

3. **Feature flag approach** (alternative to full rollback):
   - Add a `USE_TWO_STEP_EXTRACTION` flag in `config.py`.
   - Keep the old `_PROMPT` and single-call path as a fallback.
   - Route based on the flag. This allows toggling without deployment.

4. **Dependency rollback** -- If `docling` causes issues:
   - The parser router's `_parse_pdf()` already has a Gemini Vision fallback path.
   - Remove `docling` from requirements, and ALL PDFs route through Gemini Vision.
   - No code changes needed beyond removing the import.

## Open Questions

1. **Gemini model for Vision extraction** -- Should `_parse_image()` use the same `gemini-2.5-flash` model configured in `config.py`, or a specific vision-optimized model? Flash supports multimodal, but Pro might be more accurate for complex scanned documents.

2. **Async Step 2 calls** -- Should we parallelize the per-provider extraction calls in this iteration, or keep it sequential for simplicity and add parallelism later? Sequential is safer and easier to debug.

3. **CSV vs JSON final output** -- The current system outputs CSV with semicolons. The user requirement specifies pipe-delimited in the description but the existing code uses semicolons. Which delimiter should the refactored output use?

4. **docling vs PyMuPDF** -- docling is powerful but heavy. PyMuPDF (`fitz`) is lighter and handles native PDF text extraction well. Should we evaluate PyMuPDF as an alternative to docling for the PDF parsing step?

5. **Logging infrastructure** -- Should we add a proper logging configuration (handlers, formatters, log levels) in this change, or just use `logging.getLogger(__name__)` with default config and defer structured logging to a future change?

6. **`robot.py` migration timeline** -- When should `robot.py` adopt the parser router? Should we plan it as a follow-up change immediately after this one, or wait for the comparatives refactor to stabilize?
