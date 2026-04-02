# Tasks: Parser Router + Comparatives Refactoring

**Change:** parser-router-comparatives-refactor
**Total estimated time:** ~12 hours
**Last updated:** 2026-04-02

---

## PHASE 1: Setup & Dependencies (30 min)

---

### 1.1: Add tabulate to requirements.txt

**Description:** `tabulate` is required by the comparatives module to format tabular data for display or logging. Without it, the assembly step in Phase 3 will fail at import time.

**Acceptance Criteria:**
- [x] `tabulate` is present in `requirements.txt`
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `import tabulate` resolves correctly in the project virtualenv

**Estimated time:** 5 min
**Dependencies:** none
**Files affected:** `requirements.txt`

---

### 1.2: Add docling to requirements.txt

**Description:** `docling` is the primary PDF parsing library used in the parser router. It must be declared as a project dependency so it is installed in all environments (local, CI, production).

**Acceptance Criteria:**
- [x] `docling` is present in `requirements.txt`
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `from docling.document_converter import DocumentConverter` resolves in the virtualenv

**Estimated time:** 5 min
**Dependencies:** none
**Files affected:** `requirements.txt`

---

### 1.3: Add beautifulsoup4 to requirements.txt

**Description:** `beautifulsoup4` (imported as `bs4`) is used by `_parse_html()` to extract table data from HTML supplier files. It must be listed as a dependency to be available in all environments.

**Acceptance Criteria:**
- [x] `beautifulsoup4` is present in `requirements.txt`
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `from bs4 import BeautifulSoup` resolves in the virtualenv

**Estimated time:** 5 min
**Dependencies:** none
**Files affected:** `requirements.txt`

---

### 1.4: Add pytest-mock to requirements.txt

**Description:** `pytest-mock` provides the `mocker` fixture used throughout the test suite to mock external calls (Gemini API, file I/O, docling). It must be present for `pytest` to collect the tests without import errors.

**Acceptance Criteria:**
- [x] `pytest-mock` is present in `requirements.txt`
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `pytest --collect-only` finds test files without fixture errors related to `mocker`

**Estimated time:** 5 min
**Dependencies:** none
**Files affected:** `requirements.txt`

---

### 1.5: Create tests/ directory structure with __init__.py and conftest.py skeleton

**Description:** Establishes the test directory so pytest can discover tests. The `__init__.py` makes `tests/` a package. The `conftest.py` skeleton defines the shared fixtures that will be filled out in Phase 5 (mock Gemini client, sample file paths, etc.).

**Acceptance Criteria:**
- [x] `tests/` directory exists at the project root
- [x] `tests/__init__.py` is present (may be empty)
- [x] `tests/conftest.py` exists with at least a module-level docstring and a placeholder comment for fixtures
- [ ] `pytest --collect-only` runs without errors from the project root

**Estimated time:** 10 min
**Dependencies:** none
**Files affected:** `tests/__init__.py`, `tests/conftest.py`

---

## PHASE 2: Parser Router (3.5 hours)

---

### 2.1: Create app/parsers.py with exception classes (UnsupportedFormatError, ParserError)

**Description:** Creates the `app/parsers.py` module and defines the two custom exception classes that the rest of the router depends on. `UnsupportedFormatError` is raised when the file extension is not in the supported set. `ParserError` is the base class for errors that occur during parsing (wrapping lower-level exceptions with context).

**Acceptance Criteria:**
- [x] `app/parsers.py` exists
- [x] `UnsupportedFormatError(Exception)` is defined with a meaningful `__str__`
- [x] `ParserError(Exception)` is defined, accepting an `original_error` parameter
- [x] Both exceptions are importable: `from app.parsers import UnsupportedFormatError, ParserError`
- [x] Neither class has any dependency on external libraries (no imports beyond stdlib)

**Estimated time:** 15 min
**Dependencies:** none
**Files affected:** `app/parsers.py`

---

### 2.2: Implement _parse_excel() for .xlsx/.xls

**Description:** Implements the private function `_parse_excel(path: str) -> pd.DataFrame` inside `app/parsers.py`. Uses `pandas.read_excel()` to load the file and returns a raw DataFrame. Raises `ParserError` on failure, wrapping the original exception.

**Acceptance Criteria:**
- [x] `_parse_excel(path)` is implemented in `app/parsers.py`
- [x] Returns a `pd.DataFrame` on valid `.xlsx` and `.xls` files
- [x] Raises `ParserError` (not a raw `Exception`) when the file is corrupt or unreadable
- [x] Function has a docstring describing parameters and return value
- [x] `openpyxl` or `xlrd` is listed in `requirements.txt` if not already present (transitive dep of pandas)

**Estimated time:** 20 min
**Dependencies:** 2.1
**Files affected:** `app/parsers.py`, `requirements.txt`

---

### 2.3: Implement _parse_ods() for .ods

**Description:** Implements `_parse_ods(path: str) -> pd.DataFrame`. Uses `pandas.read_excel(engine='odf')` to handle OpenDocument Spreadsheet format. Raises `ParserError` on failure. The `odfpy` package must be available.

**Acceptance Criteria:**
- [x] `_parse_ods(path)` is implemented in `app/parsers.py`
- [x] Returns a `pd.DataFrame` on a valid `.ods` file
- [x] Raises `ParserError` on failure
- [ ] `odfpy` is listed in `requirements.txt`
- [x] Function has a docstring

**Estimated time:** 15 min
**Dependencies:** 2.1
**Files affected:** `app/parsers.py`, `requirements.txt`

---

### 2.4: Implement _parse_pdf() with docling + fallback to Vision

**Description:** Implements `_parse_pdf(path: str) -> pd.DataFrame`. Primary strategy: use `docling.DocumentConverter` to extract tables. Fallback strategy (when docling returns no usable table data): call `_parse_image()` after converting the PDF first page to an image. Raises `ParserError` if both strategies fail.

**Acceptance Criteria:**
- [x] `_parse_pdf(path)` is implemented in `app/parsers.py`
- [x] When docling extracts a non-empty table, returns that as a `pd.DataFrame`
- [x] When docling result is empty, falls back to `_parse_image()` (task 2.6 must exist)
- [x] Raises `ParserError` if both paths fail
- [x] Docling import is guarded: if `docling` is unavailable, jumps directly to fallback with a logged warning
- [x] Function has a docstring

**Estimated time:** 40 min
**Dependencies:** 2.1, 2.6 (can be stubbed during development), 1.2
**Files affected:** `app/parsers.py`

---

### 2.5: Implement _parse_html() with BeautifulSoup

**Description:** Implements `_parse_html(path: str) -> pd.DataFrame`. Reads the HTML file, uses `BeautifulSoup` to locate the first `<table>` element, and converts it to a DataFrame using `pandas.read_html()` or manual row extraction. Raises `ParserError` if no table is found.

**Acceptance Criteria:**
- [x] `_parse_html(path)` is implemented in `app/parsers.py`
- [x] Returns a `pd.DataFrame` when the HTML contains at least one `<table>`
- [x] Raises `ParserError` when no table is found in the document
- [x] `beautifulsoup4` import is used (not just `pandas.read_html` alone)
- [x] Function has a docstring

**Estimated time:** 25 min
**Dependencies:** 2.1, 1.3
**Files affected:** `app/parsers.py`

---

### 2.6: Implement _parse_image() with Gemini Vision + cleanup

**Description:** Implements `_parse_image(path: str) -> pd.DataFrame`. Sends the image to the Gemini Vision API with a structured prompt requesting tabular price data. Parses the JSON response into a DataFrame. Deletes any temporary file passed to it after processing (cleanup contract). Raises `ParserError` on API failure or unparseable response.

**Acceptance Criteria:**
- [x] `_parse_image(path)` is implemented in `app/parsers.py`
- [x] Calls Gemini Vision API with the image and a prompt requesting JSON-formatted table data
- [x] Parses the response into a `pd.DataFrame`
- [x] Deletes the file at `path` using `os.remove()` inside a `finally` block (so cleanup happens even on error)
- [x] Raises `ParserError` on API error or JSON parse failure
- [x] Function has a docstring

**Estimated time:** 35 min
**Dependencies:** 2.1
**Files affected:** `app/parsers.py`

---

### 2.7: Implement parse_document() router and logging

**Description:** Implements the public entry point `parse_document(path: str) -> pd.DataFrame`. Inspects the file extension (lowercased), dispatches to the appropriate private `_parse_*` function, and raises `UnsupportedFormatError` for unknown extensions. Adds `logging` calls at INFO level for each dispatch decision and at ERROR level for exceptions. This is the function consumed by `main.py`.

**Acceptance Criteria:**
- [x] `parse_document(path)` is the only public function exported from `app/parsers.py`
- [x] Routes `.xlsx` and `.xls` → `_parse_excel()`
- [x] Routes `.ods` → `_parse_ods()`
- [x] Routes `.pdf` → `_parse_pdf()`
- [x] Routes `.html`, `.htm` → `_parse_html()`
- [x] Routes `.png`, `.jpg`, `.jpeg`, `.webp` → `_parse_image()`
- [x] Raises `UnsupportedFormatError` for any other extension
- [x] `logging.getLogger(__name__)` is used (not `print`)
- [x] Function has a docstring

**Estimated time:** 20 min
**Dependencies:** 2.2, 2.3, 2.4, 2.5, 2.6
**Files affected:** `app/parsers.py`

---

## PHASE 3: Comparatives Refactoring (2.5 hours)

---

### 3.1: Create _llamar_gemini_json() helper with retry logic

**Description:** Extracts the repeated pattern of calling the Gemini API and parsing a JSON response into a single reusable helper `_llamar_gemini_json(prompt: str, max_retries: int = 3) -> dict`. Implements exponential backoff on rate-limit or transient errors. Returns the parsed dict or raises `ParserError` after exhausting retries.

**Acceptance Criteria:**
- [x] `_llamar_gemini_json(prompt, max_retries=3)` is defined in `app/robot_comparativas.py` (or a new `app/helpers.py` if the spec mandates separation)
- [x] Retries up to `max_retries` times on `429` or network-level errors with exponential backoff
- [x] Returns a `dict` parsed from the Gemini JSON response
- [x] Raises `ParserError` after all retries are exhausted
- [x] All Gemini API calls in the comparatives module are updated to use this helper (no duplicate call logic)
- [x] Function has a docstring

**Estimated time:** 30 min
**Dependencies:** none (can be developed in parallel with Phase 2)
**Files affected:** `app/robot_comparativas.py`

---

### 3.2: Create _limpiar_precio() helper

**Description:** Implements `_limpiar_precio(raw: str) -> float | None`. Normalizes price strings by stripping currency symbols, thousand separators, and whitespace, then converts to `float`. Returns `None` for values that cannot be parsed (e.g., `"N/A"`, `"-"`, empty string).

**Acceptance Criteria:**
- [x] `_limpiar_precio(raw)` is defined in `app/robot_comparativas.py`
- [x] Handles formats: `"$ 1.250,50"`, `"1250.50"`, `"1,250.50"`, `"USD 1250"`, `""`, `"N/A"`
- [x] Returns a `float` for valid prices
- [x] Returns `None` for non-parseable input (no exception raised)
- [x] Function has a docstring with input/output examples

**Estimated time:** 20 min
**Dependencies:** none
**Files affected:** `app/robot_comparativas.py`

---

### 3.3: Implement _detectar_proveedores() (Step 1)

**Description:** Implements `_detectar_proveedores(df: pd.DataFrame) -> list[str]`. Given the raw DataFrame from the parser router, calls `_llamar_gemini_json()` with a prompt asking Gemini to identify supplier names from column headers or metadata rows. Returns a list of detected supplier name strings.

**Acceptance Criteria:**
- [x] `_detectar_proveedores(df)` is defined in `app/robot_comparativas.py`
- [x] Calls `_llamar_gemini_json()` (task 3.1) — no direct Gemini API calls
- [x] Returns a non-empty `list[str]` on success
- [x] Raises `NoProvidersDetectedError` (task 3.7) when Gemini returns an empty list
- [x] Function has a docstring

**Estimated time:** 25 min
**Dependencies:** 3.1, 3.7 (can be stubbed)
**Files affected:** `app/robot_comparativas.py`

---

### 3.4: Implement _extraer_datos_proveedor() (Step 2)

**Description:** Implements `_extraer_datos_proveedor(df: pd.DataFrame, proveedor: str) -> list[dict]`. Given the DataFrame and a single supplier name, calls `_llamar_gemini_json()` with a prompt requesting structured extraction of that supplier's product/price rows. Returns a list of row dicts with normalized prices via `_limpiar_precio()`.

**Acceptance Criteria:**
- [x] `_extraer_datos_proveedor(df, proveedor)` is defined in `app/robot_comparativas.py`
- [x] Calls `_llamar_gemini_json()` (task 3.1)
- [x] Each returned dict contains at minimum: `proveedor`, `producto`, `precio` (float or None)
- [x] Prices are normalized using `_limpiar_precio()` (task 3.2)
- [x] Returns an empty list (not an exception) when the supplier has no rows
- [x] Function has a docstring

**Estimated time:** 30 min
**Dependencies:** 3.1, 3.2
**Files affected:** `app/robot_comparativas.py`

---

### 3.5: Implement _ensamblar_csv() assembly logic

**Description:** Implements `_ensamblar_csv(rows: list[dict]) -> str`. Takes the flat list of row dicts produced by iterating `_extraer_datos_proveedor()` over all detected suppliers and converts it to a CSV string (using `pandas.DataFrame.to_csv(index=False)`). Also uses `tabulate` to produce a human-readable preview logged at INFO level.

**Acceptance Criteria:**
- [x] `_ensamblar_csv(rows)` is defined in `app/robot_comparativas.py`
- [x] Returns a valid CSV string (header row + data rows)
- [x] Uses `tabulate` to log a preview table at INFO level (not returned, only logged)
- [x] Returns an empty CSV with only the header when `rows` is empty
- [x] Function has a docstring

**Estimated time:** 20 min
**Dependencies:** 3.4 (interface must be known), 1.1
**Files affected:** `app/robot_comparativas.py`

---

### 3.6: Refactor procesar_comparativa() to use new pipeline

**Description:** Replaces the monolithic implementation of `procesar_comparativa()` with an orchestration of the new pipeline: `parse_document()` → `_detectar_proveedores()` → `_extraer_datos_proveedor()` (for each supplier) → `_ensamblar_csv()`. Preserves the existing function signature so callers in `main.py` are not broken.

**Acceptance Criteria:**
- [x] `procesar_comparativa(path: str) -> str` signature is unchanged
- [x] Function body calls the four pipeline steps in order
- [x] No direct Gemini API calls remain in `procesar_comparativa()` (all delegated to helpers)
- [x] Returns the CSV string produced by `_ensamblar_csv()`
- [x] All previous inline logic (prompt building, JSON parsing, price cleaning) is removed and replaced by helper calls
- [x] Function has an updated docstring reflecting the new pipeline

**Estimated time:** 30 min
**Dependencies:** 3.3, 3.4, 3.5, 2.7
**Files affected:** `app/robot_comparativas.py`

---

### 3.7: Add NoProvidersDetectedError exception and error handling

**Description:** Defines `NoProvidersDetectedError(Exception)` in `app/robot_comparativas.py` and wires it into `_detectar_proveedores()` (task 3.3) and `procesar_comparativa()` (task 3.6). The endpoint in `main.py` must catch this and return a `422` response with a clear error message.

**Acceptance Criteria:**
- [x] `NoProvidersDetectedError` is defined in `app/robot_comparativas.py`
- [x] `_detectar_proveedores()` raises it when Gemini returns zero suppliers
- [x] `procesar_comparativa()` does NOT catch it (lets it propagate to `main.py`)
- [x] `main.py` catches `NoProvidersDetectedError` and returns HTTP `422` with `{"error": "No se detectaron proveedores en el documento"}`
- [x] Exception is importable: `from app.robot_comparativas import NoProvidersDetectedError`

**Estimated time:** 15 min
**Dependencies:** 3.3, 3.6 (can be wired after stubbing)
**Files affected:** `app/robot_comparativas.py`, `app/main.py`

---

## PHASE 4: Integration (1 hour)

---

### 4.1: Update main.py to import parse_document

**Description:** Adds `from app.parsers import parse_document, UnsupportedFormatError, ParserError` to `main.py`. Verifies that the existing import structure does not conflict. This is a prerequisite for wiring the parser router into the endpoint.

**Acceptance Criteria:**
- [x] `parse_document`, `UnsupportedFormatError`, and `ParserError` are imported in `main.py`
- [x] `python -c "from app.main import app"` exits without `ImportError`
- [x] No duplicate imports or circular dependencies introduced

**Estimated time:** 10 min
**Dependencies:** 2.7
**Files affected:** `app/main.py`

---

### 4.2: Add logging setup to main.py

**Description:** Configures the root logger in `main.py` using `logging.basicConfig()` (or a structured handler) so that log output from `app/parsers.py` and `app/robot_comparativas.py` is visible at runtime. Sets level to `INFO` by default, overridable via an environment variable (`LOG_LEVEL`).

**Acceptance Criteria:**
- [x] `logging.basicConfig(level=...)` or equivalent is called once in `main.py` at startup (not inside a route handler)
- [x] Log level defaults to `INFO`
- [x] Log level is overridable via `LOG_LEVEL` environment variable (e.g., `LOG_LEVEL=DEBUG`)
- [x] Starting the server and making a request produces at least one INFO-level log line from the parser

**Estimated time:** 15 min
**Dependencies:** 4.1
**Files affected:** `app/main.py`

---

### 4.3: Add finally block for temp file cleanup

**Description:** Wraps the file processing logic in the `POST /procesar` endpoint with a `try/finally` block to ensure that any temporary file written to disk is deleted after processing, regardless of success or failure. Prevents disk accumulation in long-running deployments.

**Acceptance Criteria:**
- [x] The endpoint handler uses `try/finally` around the processing logic
- [x] The `finally` block calls `os.remove(temp_path)` if the file exists (`os.path.exists` guard)
- [x] If the file was already cleaned up by `_parse_image()`, the guard prevents a `FileNotFoundError`
- [x] Confirmed by uploading a file and verifying the temp file is gone after the response

**Estimated time:** 15 min
**Dependencies:** 4.1
**Files affected:** `app/main.py`

---

### 4.4: Update error handling in POST /procesar endpoint

**Description:** Ensures the endpoint catches all expected exceptions from the parser and comparatives modules and returns appropriate HTTP responses. Maps each exception type to its HTTP status code and a user-facing message in Spanish.

**Acceptance Criteria:**
- [x] `UnsupportedFormatError` → HTTP `415` with `{"error": "Formato no soportado: {extension}"}`
- [x] `ParserError` → HTTP `422` with `{"error": "No se pudo procesar el archivo: {detail}"}`
- [x] `NoProvidersDetectedError` → HTTP `422` with `{"error": "No se detectaron proveedores en el documento"}`
- [x] Generic `Exception` → HTTP `500` with `{"error": "Error interno del servidor"}` (and the exception is logged at ERROR level)
- [x] No bare `except:` clauses remain in the endpoint

**Estimated time:** 20 min
**Dependencies:** 4.1, 3.7
**Files affected:** `app/main.py`

---

## PHASE 5: Testing (4 hours)

---

### 5.1: Create conftest.py with mock fixtures

**Description:** Fills out `tests/conftest.py` with shared pytest fixtures used across both test files. Fixtures include: a mock Gemini client that returns configurable JSON responses, sample file paths pointing to small test fixtures in `tests/fixtures/`, and a factory fixture for building DataFrames.

**Acceptance Criteria:**
- [ ] `tests/conftest.py` defines at minimum: `mock_gemini_client`, `sample_xlsx_path`, `sample_pdf_path`, `sample_html_path`, `sample_image_path`, `sample_ods_path`
- [ ] `tests/fixtures/` directory exists with at least one real sample file per format (or generated at fixture setup time)
- [ ] All fixtures are collected by `pytest --collect-only` without errors
- [ ] Fixtures do NOT make real network calls (all external calls are mocked)

**Estimated time:** 40 min
**Dependencies:** 1.5, 1.4
**Files affected:** `tests/conftest.py`, `tests/fixtures/` (new directory)

---

### 5.2: Write tests/test_parsers.py (9 tests for all formats)

**Description:** Creates `tests/test_parsers.py` with 9 unit tests covering `parse_document()` and the private parsers. Tests use mocked external dependencies (Gemini Vision API, docling) so no real files or network calls are needed. Covers happy paths and key error paths.

**Acceptance Criteria:**
- [ ] `tests/test_parsers.py` exists with exactly these 9 test cases (or more):
  - [ ] `test_parse_xlsx_returns_dataframe`
  - [ ] `test_parse_xls_returns_dataframe`
  - [ ] `test_parse_ods_returns_dataframe`
  - [ ] `test_parse_pdf_uses_docling`
  - [ ] `test_parse_pdf_falls_back_to_vision_when_docling_empty`
  - [ ] `test_parse_html_extracts_table`
  - [ ] `test_parse_image_calls_gemini_and_cleans_up`
  - [ ] `test_parse_document_raises_unsupported_format_error`
  - [ ] `test_parse_document_routes_to_correct_parser`
- [ ] All 9 tests pass (`pytest tests/test_parsers.py`)
- [ ] No real Gemini API calls or file I/O to external systems

**Estimated time:** 60 min
**Dependencies:** 5.1, 2.7
**Files affected:** `tests/test_parsers.py`

---

### 5.3: Write tests/test_robot_comparativas.py (9 tests for extraction)

**Description:** Creates `tests/test_robot_comparativas.py` with 9 unit tests covering the comparatives pipeline helpers and `procesar_comparativa()`. Uses `mocker` to patch `_llamar_gemini_json()` so no real API calls are made.

**Acceptance Criteria:**
- [ ] `tests/test_robot_comparativas.py` exists with exactly these 9 test cases (or more):
  - [ ] `test_limpiar_precio_handles_currency_symbols`
  - [ ] `test_limpiar_precio_returns_none_for_invalid_input`
  - [ ] `test_detectar_proveedores_returns_list`
  - [ ] `test_detectar_proveedores_raises_when_empty`
  - [ ] `test_extraer_datos_proveedor_returns_rows`
  - [ ] `test_extraer_datos_proveedor_returns_empty_list_when_no_rows`
  - [ ] `test_ensamblar_csv_produces_valid_csv`
  - [ ] `test_ensamblar_csv_returns_header_only_when_no_rows`
  - [ ] `test_procesar_comparativa_full_pipeline`
- [ ] All 9 tests pass (`pytest tests/test_robot_comparativas.py`)
- [ ] No real Gemini API calls

**Estimated time:** 60 min
**Dependencies:** 5.1, 3.6
**Files affected:** `tests/test_robot_comparativas.py`

---

### 5.4: Run pytest with coverage and verify 100% of new code

**Description:** Runs the full test suite with `pytest-cov` and verifies that all new code introduced in Phases 2 and 3 has 100% line coverage. Any uncovered lines must either be covered by adding tests or marked with `# pragma: no cover` with a justification comment.

**Acceptance Criteria:**
- [ ] `pytest-cov` (or `coverage`) is listed in `requirements.txt`
- [ ] `pytest --cov=app --cov-report=term-missing` runs without errors
- [ ] `app/parsers.py` shows 100% coverage
- [ ] `app/robot_comparativas.py` shows 100% coverage (new functions only; legacy code may be excluded)
- [ ] Any `# pragma: no cover` usage has a comment explaining why (e.g., defensive error branch for OS-level failures)
- [ ] Total test count is at least 18 (9 + 9 from tasks 5.2 and 5.3)

**Estimated time:** 30 min
**Dependencies:** 5.2, 5.3
**Files affected:** `requirements.txt`, `tests/test_parsers.py`, `tests/test_robot_comparativas.py`

---

## PHASE 6: Cleanup (1 hour)

---

### 6.1: Review code, docstrings, edge cases

**Description:** Final review pass over all new and modified files. Verifies that every public and private function has a docstring, that no debug `print()` statements remain, that all edge cases identified in the spec are handled, and that the code is consistent with the existing style in the codebase.

**Acceptance Criteria:**
- [ ] Every function in `app/parsers.py` has a docstring
- [ ] Every new function in `app/robot_comparativas.py` has a docstring
- [ ] No `print()` calls in production code (only `logging.*`)
- [ ] No TODO or FIXME comments left unaddressed
- [ ] All edge cases from the spec (empty file, corrupt file, no internet, empty Gemini response) are handled with appropriate exceptions or return values
- [ ] `pytest` still passes with 100% coverage after the review pass

**Estimated time:** 30 min
**Dependencies:** 5.4
**Files affected:** `app/parsers.py`, `app/robot_comparativas.py`, `app/main.py`

---

### 6.2: Commit changes with message

**Description:** Stages all new and modified files and creates a single conventional commit summarizing the parser router and comparatives refactoring. Follows the project's commit message convention.

**Acceptance Criteria:**
- [ ] All new files are staged: `app/parsers.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_parsers.py`, `tests/test_robot_comparativas.py`, `tests/fixtures/`
- [ ] All modified files are staged: `app/robot_comparativas.py`, `app/main.py`, `requirements.txt`
- [ ] Commit message follows conventional commits format: `feat: add parser router and refactor comparatives pipeline`
- [ ] `git log --oneline -1` shows the commit
- [ ] Working tree is clean after the commit (`git status` shows nothing to commit)

**Estimated time:** 10 min
**Dependencies:** 6.1
**Files affected:** all files from Phases 1–5

---

## Summary

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| Phase 1: Setup & Dependencies | 5 | 30 min |
| Phase 2: Parser Router | 7 | 3.5 h |
| Phase 3: Comparatives Refactoring | 7 | 2.5 h |
| Phase 4: Integration | 4 | 1 h |
| Phase 5: Testing | 4 | 4 h |
| Phase 6: Cleanup | 2 | 1 h |
| **Total** | **29** | **~12.5 h** |
