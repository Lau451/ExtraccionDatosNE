"""
Comparativas extraction pipeline: app/robot_comparativas.py

Extracts price comparison documents using Gemini with two chunking strategies:

  PDF (large, > _PDF_PAGE_THRESHOLD pages):
    1. Split PDF into overlapping page-range chunks (_PAGE_CHUNK_SIZE pages,
       _PAGE_OVERLAP overlap) using pypdf.
    2. Parse each chunk to Markdown via docling, compress, call Gemini per chunk.
    3. Merge results grouping providers by renglon number before top-3 filter.

  Other formats / small PDFs (markdown > _CHUNK_THRESHOLD chars):
    1. Parse document to Markdown, compress to reduce tokens.
    2. If small: single Gemini call. If large: split into markdown chunks of
       _CHUNK_SIZE renglones each, call Gemini per chunk, merge results.

  3. Filter: Keep only top 3 providers per renglon (Python, no API call).

Public API (signature unchanged from prior version):
  procesar_comparativa(ruta_archivo, nombre_original) -> Path

Custom Exceptions:
  NoProvidersDetectedError  -- No providers detected in the document.
  ChunkExtractionError      -- One or more chunks failed definitively after sequential retry.
"""

import csv
import json
import logging
import os
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from uuid import UUID

from google.genai import types

from app.config import CLIENT, get_output_dir, get_processed_dir, COMPARATIVAS_OUTPUT_BASE, DATA_DIR, get_next_client, generate_with_fallback
from app.robot import obtener_cliente, nombre_unico
from app.gemini_errors import handle_gemini_errors, GeminiQuotaExceededError, GeminiRateLimitError, GeminiTruncationError
from app.persistent_chunking import guardar_chunk

logger = logging.getLogger(__name__)

_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    max_output_tokens=65_536,   # gemini-2.5-flash max; prevents mid-JSON truncation
)

_CHUNK_THRESHOLD = 40_000   # chars; above this, use chunked Gemini calls
_CHUNK_SIZE = 15            # items per chunk (reduce to 10 if truncation persists in Phase 3)
_MAX_PARALLEL_CHUNKS = 3    # concurrent Gemini calls; lower to 2 on free-tier API keys

_PDF_PAGE_THRESHOLD = 20    # PDFs with more pages than this use page-based splitting
_PAGE_CHUNK_SIZE = 15       # pages per PDF chunk
_PAGE_OVERLAP = 1           # overlap pages between consecutive chunks
_GAP_RETRY_THRESHOLD = 3   # min consecutive missing renglones to trigger targeted retry

# ======================
# PROMPTS
# ======================

_PROMPT_UNIFIED = """Extract data from this price comparison document (comparativa de precios).

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
- DUPLICATES: if the same product description appears in multiple consecutive rows, they belong to the SAME renglon — assign them the same renglon number and merge all their provider prices together

NUMBER FORMAT — CRITICAL:
Copy "precio" VERBATIM from the document — every digit, dot, and comma exactly as printed.
Do NOT evaluate, convert, round, or normalize any number.
If the document shows "20.227,00" → return "20.227,00". If it shows "4,650.00" → return "4,650.00". If it shows "362.50" → return "362.50"."""

# ======================
# CUSTOM EXCEPTIONS
# ======================


class NoProvidersDetectedError(ValueError):
    """Raised when a comparatives document has no detectable providers.

    Inherits from ValueError (same base as ParserError from parsers.py) so
    callers can catch it specifically or as a broader ValueError.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ChunkExtractionError(RuntimeError):
    """Raised when one or more chunks fail definitively after sequential retry.

    Signals that the output CSV would be incomplete. No CSV is written.
    Attributes:
        failed_chunks: 1-based indices of the chunks that could not be processed.
    """

    def __init__(self, failed_chunks: list[int]):
        self.failed_chunks = failed_chunks
        count = len(failed_chunks)
        indices = ", ".join(str(i) for i in failed_chunks)
        super().__init__(
            f"{count} chunk(s) fallaron definitivamente tras reintento secuencial "
            f"(chunks: {indices}). El CSV no fue generado para evitar datos incompletos."
        )


# ======================
# HELPERS
# ======================


@handle_gemini_errors(max_retries=4, backoff_factor=40.0)
def _llamar_gemini_pdf(prompt: str, pdf_bytes: bytes) -> dict:
    """Call Gemini with a PDF as inline_data (vision) instead of markdown text.

    Used by the page-based chunking flow to bypass docling's lossy table parsing.
    Gemini reads the PDF structure natively, capturing all providers per renglon.
    """
    client = get_next_client()
    contents = [
        types.Content(parts=[
            types.Part(text=prompt),
            types.Part(inline_data=types.Blob(mime_type="application/pdf", data=pdf_bytes)),
        ])
    ]
    response = generate_with_fallback(client, contents, config=_JSON_CONFIG)

    finish_reason = None
    if response.candidates:
        finish_reason = str(response.candidates[0].finish_reason)

    logger.info(
        "Gemini PDF vision response: %d chars, finish_reason=%s",
        len(response.text), finish_reason,
    )

    if finish_reason and "MAX_TOKENS" in finish_reason:
        raise GeminiTruncationError(
            f"Respuesta truncada en {len(response.text)} chars (finish_reason={finish_reason})"
        )

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise GeminiTruncationError(
            f"JSON inválido tras {len(response.text)} chars "
            f"(finish_reason={finish_reason}): {exc}"
        ) from exc

    if isinstance(result, list):
        logger.warning(
            "Respuesta como lista en lugar de dict (%d items) — inferiendo estructura",
            len(result),
        )
        if result and isinstance(result[0], dict):
            first = result[0]
            if "renglones" in first:
                return first
            if "renglon" in first:
                return {"proveedores": [], "renglones": result}
        return {"proveedores": [], "renglones": []}

    return result


@handle_gemini_errors(max_retries=4, backoff_factor=40.0)
def _llamar_gemini_json(prompt: str, markdown: str) -> dict:
    """Call Gemini with response_mime_type='application/json' for guaranteed valid JSON.

    Checks finish_reason BEFORE parsing to detect truncation early. Raises
    GeminiTruncationError (not retried) instead of letting JSONDecodeError
    trigger pointless retries on a deterministically-too-large chunk.

    Raises:
        GeminiTruncationError: Response truncated (MAX_TOKENS) or invalid JSON.
        GeminiQuotaExceededError: API quota exceeded.
        GeminiRateLimitError: API rate limit / 429 / 503 — retried with backoff.
    """
    client = get_next_client()
    response = generate_with_fallback(client, f"{prompt}\n\n{markdown}", config=_JSON_CONFIG)

    finish_reason = None
    if response.candidates:
        finish_reason = str(response.candidates[0].finish_reason)

    logger.info(
        "Gemini response: %d chars, finish_reason=%s",
        len(response.text), finish_reason,
    )

    if finish_reason and "MAX_TOKENS" in finish_reason:
        raise GeminiTruncationError(
            f"Respuesta truncada en {len(response.text)} chars (finish_reason={finish_reason})"
        )

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise GeminiTruncationError(
            f"JSON inválido tras {len(response.text)} chars "
            f"(finish_reason={finish_reason}): {exc}"
        ) from exc

    if isinstance(result, list):
        logger.warning(
            "Respuesta como lista en lugar de dict (%d items) — inferiendo estructura",
            len(result),
        )
        if result and isinstance(result[0], dict):
            first = result[0]
            if "renglones" in first:
                # Wrapped dict: [{"proveedores": [...], "renglones": [...]}]
                return first
            if "renglon" in first:
                # List of renglon dicts directly
                return {"proveedores": [], "renglones": result}
        return {"proveedores": [], "renglones": []}

    return result


def _limpiar_precio(raw: str) -> str:
    """Clean a price string to numeric format, handling Argentine conventions.

    Returns empty string for missing/invalid values. Handles:
      - Argentine format: "1.234,56" -> "1234.56"
      - Comma-only decimal: "12,34" -> "12.34"
      - US format: "1,234.56" -> "1234.56"
      - Currency symbols: "$", "€", "USD", "ARS"
      - Non-parseable values: returns "" and logs a WARNING

    Args:
        raw: Raw price string (e.g., "$1.234,56", "12,5", "no cotiza").

    Returns:
        Numeric string with 2 decimal places (e.g., "12.34"), or "" if
        the value is missing, non-numeric, or explicitly invalid.

    Examples:
        >>> _limpiar_precio("$1.234,56")  -> "1234.56"
        >>> _limpiar_precio("12,34")       -> "12.34"
        >>> _limpiar_precio("no cotiza")   -> ""
        >>> _limpiar_precio("")            -> ""
    """
    if not raw:
        return ""

    stripped = raw.strip()
    if stripped.lower() in ("", "-", "n/a", "no cotiza", "no cotiza", "sin precio", "s/p"):
        return ""

    # Strip currency symbols and whitespace
    cleaned = re.sub(r"[$€\s]|USD|ARS", "", stripped)

    if not cleaned:
        return ""

    # Determine format by which separator appears last (= decimal separator)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(".") > cleaned.rfind(","):
            # US format: "1,234.56" → dot is decimal, comma is thousands
            cleaned = cleaned.replace(",", "")
        else:
            # Argentine format: "1.234,56" → comma is decimal, dot is thousands
            cleaned = cleaned.replace(".", "").replace(",", ".")
    # Handle comma-only decimal: "12,34"
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    # Handle multiple dots: "8.100.00000" → last dot is decimal, rest are thousands
    elif cleaned.count(".") > 1:
        integer_part, decimal_part = cleaned.rsplit(".", 1)
        cleaned = integer_part.replace(".", "") + "." + decimal_part
    # else: single dot "1234.56" — no change needed

    try:
        value = float(cleaned)
        return f"{value:.2f}"
    except ValueError:
        logger.warning("Non-numeric price, leaving empty: '%s'", raw)
        return ""


def _guardar_docling_output(
    contenido_extraido: str,
    nombre_base: str,
    cliente: str,
) -> Path:
    """Guarda la salida del parser (docling) en data/Salida/docling_output/

    Args:
        contenido_extraido: El contenido extraído por el parser
        nombre_base: Nombre base del archivo original (sin extensión)
        cliente: ID del cliente/origen

    Returns:
        Path al archivo guardado
    """
    docling_dir = DATA_DIR / "Salida" / "docling_output" / cliente
    docling_dir.mkdir(parents=True, exist_ok=True)

    # Generar nombre único si el archivo ya existe
    nombre_salida = nombre_unico(nombre_base, docling_dir, ".md")
    ruta_salida = docling_dir / nombre_salida

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(contenido_extraido)

    logger.info("Saved docling output: %s (%d chars)", ruta_salida, len(contenido_extraido))
    return ruta_salida


def _comprimir_markdown(markdown: str) -> str:
    """Compress Markdown to reduce tokens before sending to Gemini.

    Removes unnecessary whitespace and formatting:
      - Collapses 3+ consecutive blank lines into 1
      - Strips trailing whitespace from each line
      - Removes lines that are only whitespace

    Args:
        markdown: Document content as a Markdown string.

    Returns:
        Compressed Markdown string.
    """
    # Collapse 3+ consecutive newlines into 2 (one blank line)
    text = re.sub(r'\n{3,}', '\n\n', markdown)

    # Strip trailing whitespace per line and remove empty-only lines
    lines = [line.rstrip() for line in text.split('\n')]
    lines = [line for line in lines if line.strip()]

    result = '\n'.join(lines)

    reduction_pct = ((len(markdown) - len(result)) / len(markdown) * 100) if markdown else 0
    logger.info(
        "Markdown compressed: %d → %d chars (%.1f%% reduction)",
        len(markdown),
        len(result),
        reduction_pct,
    )

    return result


def _restructurar_si_formato_plano(markdown: str) -> str:
    """Detect flat-text PDF markdown and restructure into explicit item sections.

    Some PDFs are parsed by docling into a table where each page's entire
    content collapses into a single huge cell. Item boundaries appear as
    "Item: - N -" markers buried within that cell text, making them easy
    for Gemini to miss.

    This function detects that pattern and splits the flat text into clearly
    delimited Markdown sections — one "## Item N" heading per item — so
    Gemini receives explicit boundaries and extracts all items reliably.

    Returns the original markdown unchanged when the flat-text pattern is
    not detected (safe for all other document formats).
    """
    if not re.search(r'Item:\s*-\s*\d+\s*-', markdown):
        return markdown

    # Extract text from the first non-empty cell of each table data row.
    # In the flat format, all real content lands in cell[0]; the rest are empty.
    text_parts: list[str] = []
    for line in markdown.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        # Skip separator rows (|---|---|)
        if re.match(r'\|[\s|:-]{3,}', stripped):
            continue
        cells = [c.strip() for c in stripped.split('|') if c.strip()]
        if cells and len(cells[0]) > 20 and re.search(r'\d', cells[0]):
            text_parts.append(cells[0])

    if not text_parts:
        return markdown

    flat = ' '.join(text_parts)

    # Split into segments using "Item: - N -" as delimiters.
    # re.split with a capturing group keeps the delimiter in the result list,
    # producing: [pre, marker1, body1, marker2, body2, ...]
    segments = re.split(r'(Item:\s*-\s*\d+\s*-)', flat)

    sections: list[str] = []
    for i in range(1, len(segments), 2):
        marker = segments[i]
        body = segments[i + 1].strip() if i + 1 < len(segments) else ''
        item_num = re.search(r'\d+', marker).group()
        sections.append(f'## Item {item_num}')
        sections.append(body)
        sections.append('')

    if not sections:
        return markdown

    restructured = '\n'.join(sections)
    logger.info(
        "Flat-text markdown detected and restructured: %d items extracted (%d → %d chars)",
        len(sections) // 3,
        len(markdown),
        len(restructured),
    )
    return restructured


def _detectar_gaps(
    renglones: list[dict],
    min_size: int = _GAP_RETRY_THRESHOLD,
) -> list[tuple[int, int]]:
    """Find suspicious numeric gaps in the merged renglon sequence.

    Small gaps (< min_size) are common in documents that legitimately skip
    item numbers. Only gaps of min_size or more are worth a retry.

    Args:
        renglones: All extracted renglon dicts (merged from all chunks).
        min_size: Minimum number of consecutive missing items to report.

    Returns:
        Sorted list of (lo, hi) inclusive ranges of missing item numbers.
    """
    nums: set[int] = set()
    for r in renglones:
        try:
            nums.add(int(float(r["renglon"])))
        except (KeyError, TypeError, ValueError):
            pass
    sorted_nums = sorted(nums)
    gaps: list[tuple[int, int]] = []
    for i in range(len(sorted_nums) - 1):
        lo = sorted_nums[i] + 1
        hi = sorted_nums[i + 1] - 1
        if hi >= lo and (hi - lo + 1) >= min_size:
            gaps.append((lo, hi))
    return gaps


def _prompt_con_foco(numeros: list[int]) -> str:
    """Return a focused extraction prompt that names specific missing item numbers.

    Appended after the base prompt so Gemini re-examines the document
    looking for items it may have skipped.
    """
    nums_str = ", ".join(str(n) for n in sorted(numeros))
    return (
        f"{_PROMPT_UNIFIED}\n\n"
        f"ATTENTION: Look specifically for items numbered {nums_str} — "
        "they may be present but were missed in a previous pass. "
        "Return an empty renglones list only if the items are genuinely absent."
    )


def _reintentar_gaps(
    gaps: list[tuple[int, int]],
    chunk_markdowns: list[str],
    chunk_results: list[dict],
) -> tuple[list[dict], list[str]]:
    """Retry specific chunks with a focused prompt for known missing item ranges.

    For each gap, identifies which chunks (by index range bracketed between the
    chunk that has the item just before the gap and the chunk that has the item
    just after) likely contain the missing items, then calls Gemini with a
    prompt that explicitly names the missing item numbers.

    Chunks with 0 renglones that fall between bracketing chunks are also
    retried — this handles the case where a chunk returned an empty result
    without raising an exception.

    Args:
        gaps: List of (lo, hi) inclusive ranges to recover.
        chunk_markdowns: Parsed+compressed markdown per chunk (index-aligned).
        chunk_results: Extraction result dict per chunk (index-aligned).

    Returns:
        Tuple (new_renglones, new_providers) with newly recovered items.
    """
    if not gaps:
        return [], []

    # Build per-chunk integer renglon sets for adjacency lookup
    chunk_nums: list[set[int]] = []
    for result in chunk_results:
        nums: set[int] = set()
        for r in result.get("renglones", []):
            try:
                nums.add(int(float(r["renglon"])))
            except (KeyError, TypeError, ValueError):
                pass
        chunk_nums.append(nums)

    new_renglones: list[dict] = []
    new_providers: list[str] = []
    retried: set[int] = set()

    for lo, hi in gaps:
        missing = list(range(lo, hi + 1))

        # Find the last chunk whose results include lo-1 (item before gap)
        # and the first chunk whose results include hi+1 (item after gap).
        before_idx: Optional[int] = None
        after_idx: Optional[int] = None
        for i, nums in enumerate(chunk_nums):
            if (lo - 1) in nums:
                before_idx = i
            if after_idx is None and (hi + 1) in nums:
                after_idx = i

        if before_idx is not None and after_idx is not None:
            target = list(range(before_idx, after_idx + 1))
        elif before_idx is not None:
            target = [before_idx]
        elif after_idx is not None:
            target = [after_idx]
        else:
            logger.warning(
                "Gap [%d-%d]: sin chunks adyacentes detectados — se omite el retry",
                lo, hi,
            )
            continue

        for idx in target:
            if idx in retried or not chunk_markdowns[idx]:
                continue
            retried.add(idx)

            # Pre-check: verify at least one missing item number appears in the
            # chunk markdown before spending an API call. Items absent from the
            # markdown are genuinely missing from the document — not a Gemini miss.
            # Exception: a chunk with 0 renglones despite having content is a
            # Gemini failure — always retry regardless of pattern match.
            chunk_md = chunk_markdowns[idx]
            chunk_renglones = len(chunk_results[idx].get("renglones", []))
            if chunk_renglones == 0 and chunk_md:
                items_en_markdown = True
                logger.info(
                    "Gap [%d-%d] chunk %d: 0 renglones con markdown no vacío — "
                    "fallo de Gemini, forzando retry",
                    lo, hi, idx + 1,
                )
            else:
                items_en_markdown = any(
                    re.search(rf'##\s*Item\s+{n}\b', chunk_md)
                    or re.search(rf'Item[:\s\-]*\b{n}\b', chunk_md)
                    or re.search(rf'(?:^|\|)\s*{n}\s*(?:\||$)', chunk_md, re.MULTILINE)
                    for n in missing
                )
            if not items_en_markdown:
                logger.info(
                    "Gap [%d-%d] chunk %d: items %s ausentes en markdown — "
                    "salto real en el documento, sin retry",
                    lo, hi, idx + 1, missing,
                )
                continue

            logger.info(
                "Gap retry [%d-%d]: chunk %d — items %s presentes en markdown, llamando a Gemini",
                lo, hi, idx + 1, missing,
            )
            try:
                retry_result = _llamar_gemini_json(
                    _prompt_con_foco(missing), chunk_markdowns[idx]
                )
                recovered = []
                missing_set = set(missing)
                for r in retry_result.get("renglones", []):
                    try:
                        if int(float(r["renglon"])) in missing_set:
                            recovered.append(r)
                    except (KeyError, TypeError, ValueError):
                        pass

                if recovered:
                    found_nums = sorted(int(float(r["renglon"])) for r in recovered)
                    logger.info(
                        "Gap retry chunk %d: recuperados %d items %s",
                        idx + 1, len(recovered), found_nums,
                    )
                    new_renglones.extend(recovered)
                    for p in retry_result.get("proveedores", []):
                        if p not in new_providers:
                            new_providers.append(p)
                else:
                    logger.info(
                        "Gap retry chunk %d: items %s confirmados ausentes en el documento",
                        idx + 1, missing,
                    )
            except Exception as exc:
                logger.warning(
                    "Gap retry chunk %d falló (%s: %s) — se continúa sin esos items",
                    idx + 1, type(exc).__name__, exc,
                )

    return new_renglones, new_providers


# ======================
# PIPELINE STEPS
# ======================


def _split_markdown_chunks(markdown: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split a markdown table into chunks, keeping Items complete.

    Groups rows by Item (identified by a number in the first column that looks
    like an item number). Each Item includes its header row + all provider rows
    that follow it. Chunks contain complete Items only — never splits an Item
    across chunks. This preserves the logical structure of the document.

    Args:
        markdown: Full markdown table from df.to_markdown(index=False).
        chunk_size: Maximum number of Items per chunk.

    Returns:
        List of markdown strings ready to be sent to Gemini individually.
    """
    lines = markdown.split("\n")
    if len(lines) < 3:
        return [markdown]

    md_header = lines[:2]   # column names + separator
    data_lines = lines[2:]

    # Detect table header repetitions (|---|---|---|...)
    # and extract document context (everything before first actual item)
    context_end = 0
    for i, line in enumerate(data_lines):
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells:
            continue
        try:
            # Check if this is an item header (number in first column, not separator)
            if cells[0] != "---" and float(cells[0]) > 0:
                context_end = i
                break
        except ValueError:
            pass

    context = data_lines[:context_end]
    body = data_lines[context_end:]

    if not body:
        return [markdown]

    # Group body lines into Items. An Item starts with a row where the first
    # cell is a number >= 1. All following rows (providers) belong to that Item
    # until the next Item header.
    items = []
    current_item = []

    for line in body:
        cells = [c.strip() for c in line.split("|") if c.strip()]

        # Skip empty lines and table header separators
        if not cells or cells[0] == "---":
            if current_item:
                current_item.append(line)
            continue

        # Check if this is an Item header (number in first column)
        is_item_header = False
        try:
            num = float(cells[0])
            if num > 0:
                is_item_header = True
        except ValueError:
            pass

        if is_item_header and current_item:
            # Start of new Item — save the previous one
            items.append(current_item)
            current_item = [line]
        else:
            # Provider row or continuation — add to current item
            current_item.append(line)

    # Don't forget the last item
    if current_item:
        items.append(current_item)

    if not items:
        return [markdown]

    # In flat-text format (no | delimiters), the splitter mistakes quantities for
    # item headers, producing "orphan" items that are just a single number line
    # (the real renglon number) followed by a separate item starting with the
    # quantity. Merge each single-line numeric orphan with the next item so chunk
    # boundaries never fall between a renglon number and its data.
    merged: list[list[str]] = []
    i = 0
    while i < len(items):
        item = items[i]
        non_empty = [ln for ln in item if ln.strip()]
        if len(non_empty) == 1 and i + 1 < len(items):
            try:
                float(non_empty[0].strip())
                merged.append(item + items[i + 1])
                i += 2
                continue
            except ValueError:
                pass
        merged.append(item)
        i += 1
    items = merged

    # Build chunks: each chunk contains up to chunk_size complete Items
    chunks = []
    for i in range(0, len(items), chunk_size):
        chunk_items = items[i : i + chunk_size]
        chunk_lines = md_header + context + [line for item in chunk_items for line in item]
        chunk = "\n".join(chunk_lines)
        chunks.append(chunk)

    return chunks


def _split_chunk_in_half(chunk: str) -> list[str]:
    """Split a markdown chunk into two halves by item count.

    Used as fallback when a chunk is too large for Gemini's output limit.
    Returns [chunk] unchanged if the chunk can't be split (≤1 item).
    """
    lines = chunk.split("\n")
    if len(lines) < 4:
        return [chunk]

    md_header = lines[:2]
    data_lines = lines[2:]
    items: list[list[str]] = []
    current_item: list[str] = []

    for line in data_lines:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells or cells[0] == "---":
            if current_item:
                current_item.append(line)
            continue
        is_item_header = False
        try:
            if float(cells[0]) > 0:
                is_item_header = True
        except ValueError:
            pass
        if is_item_header and current_item:
            items.append(current_item)
            current_item = [line]
        else:
            current_item.append(line)
    if current_item:
        items.append(current_item)

    if len(items) <= 1:
        return [chunk]

    mid = max(1, len(items) // 2)

    def _build(item_list: list[list[str]]) -> str:
        return "\n".join(md_header + [ln for item in item_list for ln in item])

    return [_build(items[:mid]), _build(items[mid:])]


def _process_chunk(prompt: str, chunk: str, chunk_idx: int, total: int) -> dict:
    """Process a single chunk; split in half automatically on truncation.

    On GeminiTruncationError: logs the event, splits the chunk in half,
    processes each half independently, and merges the results. Truncation errors
    on individual sub-chunks are caught and produce empty results for that half
    rather than raising and discarding the entire chunk.
    """
    try:
        return _llamar_gemini_json(prompt, chunk)
    except GeminiTruncationError:
        logger.info(
            "Chunk %d/%d truncado — dividiendo en 2 subchunks",
            chunk_idx, total,
        )
        sub_chunks = _split_chunk_in_half(chunk)
        if len(sub_chunks) < 2:
            logger.warning("Chunk %d no se pudo dividir — renglones vacíos", chunk_idx)
            return {"proveedores": [], "renglones": []}

        partial: list[dict] = []
        for sc_idx, sc in enumerate(sub_chunks, start=1):
            try:
                partial.append(_llamar_gemini_json(prompt, sc))
            except GeminiTruncationError:
                logger.warning(
                    "Subchunk %d del chunk %d también truncado — se omite esa mitad",
                    sc_idx, chunk_idx,
                )
                partial.append({"proveedores": [], "renglones": []})
            except Exception as exc:
                logger.error(
                    "Subchunk %d del chunk %d falló (%s: %s) — se omite esa mitad",
                    sc_idx, chunk_idx, type(exc).__name__, exc,
                )
                partial.append({"proveedores": [], "renglones": []})

        r1, r2 = partial
        merged_providers = list(dict.fromkeys(
            r1.get("proveedores", []) + r2.get("proveedores", [])
        ))
        logger.info(
            "Subchunks de chunk %d resueltos: %d + %d renglones",
            chunk_idx,
            len(r1.get("renglones", [])),
            len(r2.get("renglones", [])),
        )
        return {
            "proveedores": merged_providers,
            "renglones": r1.get("renglones", []) + r2.get("renglones", []),
        }


def _extraer_comparativa(markdown: str, filepath: Path, *, session_id: Optional[UUID] = None) -> dict:
    """Extract providers and all items with prices from a comparativa document.

    Processes chunks in parallel (up to _MAX_PARALLEL_CHUNKS concurrent Gemini
    calls). Each chunk is handled by _process_chunk which auto-splits on
    GeminiTruncationError. Results are merged in original order.

    Args:
        markdown: Compressed document content as a Markdown string.
        filepath: Original file path — used only in error messages.

    Returns:
        Dict with keys "proveedores" (list[str]) and "renglones" (list[dict]).

    Raises:
        NoProvidersDetectedError: If no providers detected across all chunks.
    """
    chunks = _split_markdown_chunks(markdown) if len(markdown) > _CHUNK_THRESHOLD else [markdown]
    total = len(chunks)

    if total > 1:
        logger.info(
            "Large document (%d chars): %d chunks of ~%d renglones, %d workers",
            len(markdown), total, _CHUNK_SIZE, min(_MAX_PARALLEL_CHUNKS, total),
        )

    results: list[Optional[dict]] = [None] * total
    workers = min(_MAX_PARALLEL_CHUNKS, total)
    failed_parallel: list[int] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(_process_chunk, _PROMPT_UNIFIED, chunk, i + 1, total): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
                logger.info(
                    "Chunk %d/%d completado: %d renglones",
                    idx + 1, total,
                    len((results[idx] or {}).get("renglones", [])),
                )
            except Exception as exc:
                logger.error(
                    "Chunk %d/%d falló en paralelo (%s: %s) — se reintentará secuencial",
                    idx + 1, total, type(exc).__name__, exc,
                )
                failed_parallel.append(idx)

    failed_definitive: list[int] = []

    if failed_parallel:
        logger.info(
            "Reintentando %d chunks fallidos secuencialmente: %s",
            len(failed_parallel),
            [i + 1 for i in failed_parallel],
        )
        for idx in failed_parallel:
            try:
                results[idx] = _process_chunk(_PROMPT_UNIFIED, chunks[idx], idx + 1, total)
                logger.info(
                    "Chunk %d/%d resuelto en reintento secuencial: %d renglones",
                    idx + 1, total,
                    len((results[idx] or {}).get("renglones", [])),
                )
            except Exception as exc:
                logger.error(
                    "Chunk %d/%d falló definitivamente tras reintento secuencial (%s: %s)",
                    idx + 1, total, type(exc).__name__, exc,
                )
                failed_definitive.append(idx + 1)
                results[idx] = {"proveedores": [], "renglones": []}

    if failed_definitive:
        raise ChunkExtractionError(failed_definitive)

    all_renglones: list[dict] = []
    providers: list[str] = []

    for idx, result in enumerate(results):
        if not result:
            continue
        for p in result.get("proveedores", []):
            if p not in providers:
                providers.append(p)
        all_renglones.extend(result.get("renglones", []))

        if session_id:
            try:
                guardar_chunk(session_id=session_id, chunk_num=idx, resultado_json=result)
            except Exception as exc:
                logger.warning("Error guardando chunk %d en Supabase: %s", idx, exc)

    if not providers:
        raise NoProvidersDetectedError(
            f"No providers detected in document '{filepath.name}'. "
            "The document may not be a valid price comparison, or the format is unrecognized."
        )

    # Gap detection: retry chunks with focused prompt for missing item ranges
    gaps = _detectar_gaps(all_renglones)
    if gaps:
        logger.warning(
            "Gaps detectados en resultado final: %s — iniciando retry con foco",
            gaps,
        )
        safe_results = [r or {"proveedores": [], "renglones": []} for r in results]
        extra_renglones, extra_providers = _reintentar_gaps(gaps, chunks, safe_results)
        all_renglones.extend(extra_renglones)
        for p in extra_providers:
            if p not in providers:
                providers.append(p)

    logger.info(
        "Detected %d providers in '%s': %s", len(providers), filepath.name, providers,
    )
    logger.info("Total renglones extracted: %d from %d chunks", len(all_renglones), total)
    return {"proveedores": providers, "renglones": all_renglones}


# ======================
# PDF PAGE-BASED CHUNKING
# ======================


def _split_pdf_by_pages(
    ruta_pdf: Path,
    pages_per_chunk: int = _PAGE_CHUNK_SIZE,
    overlap: int = _PAGE_OVERLAP,
) -> list[Path]:
    """Split a PDF into overlapping page-range temp files using pypdf.

    Each chunk contains `pages_per_chunk` pages. Consecutive chunks share
    `overlap` pages so items that fall on a boundary appear complete in at
    least one chunk.

    Args:
        ruta_pdf: Path to the source PDF.
        pages_per_chunk: Maximum pages per chunk.
        overlap: Pages shared between consecutive chunks.

    Returns:
        List of temp PDF paths. Caller is responsible for deleting them.
    """
    from pypdf import PdfReader, PdfWriter  # noqa: PLC0415

    reader = PdfReader(str(ruta_pdf))
    total = len(reader.pages)
    step = max(1, pages_per_chunk - overlap)
    chunks: list[Path] = []

    for start in range(0, total, step):
        end = min(start + pages_per_chunk, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        fd, tmp_str = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        tmp_path = Path(tmp_str)
        with open(tmp_path, "wb") as f:
            writer.write(f)
        chunks.append(tmp_path)

        if end >= total:
            break

    logger.info(
        "PDF split: %d pages → %d chunks (%d pages/chunk, %d overlap)",
        total, len(chunks), pages_per_chunk, overlap,
    )
    return chunks


def _procesar_chunk_pdf(
    chunk_path: Path, chunk_idx: int, total: int
) -> tuple[str, dict]:
    """Extract a PDF page-chunk via Gemini vision (inline_data).

    Sends the raw PDF bytes directly to Gemini instead of converting to Markdown
    via docling. This preserves multi-column table structure that docling loses,
    allowing Gemini to capture all providers per renglon.

    Falls back to docling+markdown if vision call truncates.

    Returns the raw pypdf text alongside the extraction result so the caller
    can keep it for gap-detection retries without re-reading the deleted temp PDF.

    Args:
        chunk_path: Path to the temp PDF chunk.
        chunk_idx: 1-based index for logging.
        total: Total number of chunks for logging.

    Returns:
        Tuple of (raw_text_for_gap_detection, result_dict).
    """
    from pypdf import PdfReader  # noqa: PLC0415

    pdf_bytes = chunk_path.read_bytes()

    # Extract raw text via pypdf — used only for gap-detection checks,
    # not sent to Gemini. pypdf preserves all provider rows even when
    # column order is scrambled.
    try:
        reader = PdfReader(str(chunk_path))
        raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("pypdf text extraction failed for chunk %d: %s", chunk_idx, exc)
        raw_text = ""

    logger.info(
        "PDF chunk %d/%d: %d bytes → Gemini vision",
        chunk_idx, total, len(pdf_bytes),
    )

    try:
        result = _llamar_gemini_pdf(_PROMPT_UNIFIED, pdf_bytes)
    except GeminiTruncationError:
        logger.warning(
            "PDF chunk %d/%d vision truncated — falling back to docling+markdown",
            chunk_idx, total,
        )
        from app.parsers import parse_document  # noqa: PLC0415
        markdown = parse_document(chunk_path)
        markdown = _restructurar_si_formato_plano(markdown)
        markdown = _comprimir_markdown(markdown)
        raw_text = markdown
        result = _process_chunk(_PROMPT_UNIFIED, markdown, chunk_idx, total)

    logger.info(
        "PDF chunk %d/%d completed: %d renglones",
        chunk_idx, total, len(result.get("renglones", [])),
    )
    return raw_text, result


def _extraer_comparativa_por_paginas(
    ruta_pdf: Path,
    *,
    session_id: Optional[UUID] = None,
    nombre_base: str = "",
    cliente: str = "",
) -> dict:
    """Extract providers and renglones from a large PDF using page-based chunking.

    Splits the PDF into overlapping chunks, processes them in parallel via
    Gemini, then merges. Temp files are deleted after processing regardless
    of success or failure.

    Args:
        ruta_pdf: Path to the source PDF.
        session_id: Optional session UUID for Supabase partial-result persistence.

    Returns:
        Dict with "proveedores" (list[str]) and "renglones" (list[dict]).

    Raises:
        NoProvidersDetectedError: If no providers detected across all chunks.
    """
    chunk_paths = _split_pdf_by_pages(ruta_pdf)
    total = len(chunk_paths)
    workers = min(_MAX_PARALLEL_CHUNKS, total)

    results: list[Optional[dict]] = [None] * total
    markdowns: list[str] = [""] * total
    failed_parallel: list[int] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(_procesar_chunk_pdf, chunk_paths[i], i + 1, total): i
            for i in range(total)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                markdowns[idx], results[idx] = future.result()
                logger.info(
                    "PDF chunk %d/%d completado: %d renglones",
                    idx + 1, total,
                    len((results[idx] or {}).get("renglones", [])),
                )
            except Exception as exc:
                logger.error(
                    "PDF chunk %d/%d falló en paralelo (%s: %s) — se reintentará secuencial",
                    idx + 1, total, type(exc).__name__, exc,
                )
                failed_parallel.append(idx)
            finally:
                if idx not in failed_parallel:
                    try:
                        chunk_paths[idx].unlink(missing_ok=True)
                    except Exception:
                        pass

    failed_definitive: list[int] = []

    if failed_parallel:
        logger.info(
            "Reintentando %d PDF chunks fallidos secuencialmente: %s",
            len(failed_parallel),
            [i + 1 for i in failed_parallel],
        )
        for idx in failed_parallel:
            try:
                markdowns[idx], results[idx] = _procesar_chunk_pdf(
                    chunk_paths[idx], idx + 1, total
                )
                logger.info(
                    "PDF chunk %d/%d resuelto en reintento secuencial: %d renglones",
                    idx + 1, total,
                    len((results[idx] or {}).get("renglones", [])),
                )
            except Exception as exc:
                logger.error(
                    "PDF chunk %d/%d falló definitivamente tras reintento secuencial (%s: %s)",
                    idx + 1, total, type(exc).__name__, exc,
                )
                failed_definitive.append(idx + 1)
                results[idx] = {"proveedores": [], "renglones": []}
            finally:
                try:
                    chunk_paths[idx].unlink(missing_ok=True)
                except Exception:
                    pass

    if failed_definitive:
        raise ChunkExtractionError(failed_definitive)

    all_renglones: list[dict] = []
    providers: list[str] = []

    safe_results = [r or {"proveedores": [], "renglones": []} for r in results]

    for idx, result in enumerate(safe_results):
        for p in result.get("proveedores", []):
            if p not in providers:
                providers.append(p)
        all_renglones.extend(result.get("renglones", []))

        if session_id:
            try:
                guardar_chunk(session_id=session_id, chunk_num=idx, resultado_json=result)
            except Exception as exc:
                logger.warning("Error guardando chunk %d en Supabase: %s", idx, exc)

    if not providers:
        raise NoProvidersDetectedError(
            f"No providers detected in PDF '{ruta_pdf.name}' across {total} page-chunks. "
            "The document may not be a valid price comparison, or the format is unrecognized."
        )

    if nombre_base and cliente:
        combined = "\n\n---\n\n".join(
            f"<!-- chunk {i+1}/{total} -->\n{md}" for i, md in enumerate(markdowns) if md
        )
        _guardar_docling_output(combined, nombre_base, cliente)

    # Gap detection: if Gemini missed items in any chunk, retry with focused prompt
    gaps = _detectar_gaps(all_renglones)
    if gaps:
        logger.warning(
            "Gaps detectados en resultado final: %s — iniciando retry con foco",
            gaps,
        )
        extra_renglones, extra_providers = _reintentar_gaps(gaps, markdowns, safe_results)
        all_renglones.extend(extra_renglones)
        for p in extra_providers:
            if p not in providers:
                providers.append(p)

    logger.info(
        "Page-chunks: %d providers, %d renglones from %d chunks",
        len(providers), len(all_renglones), total,
    )
    return {"proveedores": providers, "renglones": all_renglones}


def _filtrar_top_3_por_renglon(all_data: dict, cliente: str) -> list[dict]:
    """Filter extracted data to keep only top 3 providers per renglon by price.

    First groups all providers for the same renglon number (handles duplicates
    from page-overlap chunking), then sorts by price and keeps the top 3.

    Args:
        all_data: Dict with "proveedores" and "renglones" keys.
        cliente: Client name derived from the filename.

    Returns:
        List of row dicts with keys: renglon, proveedor, marca,
        precio, cliente — ready for csv.DictWriter. At most 3 rows
        per renglon, ordered by ascending price.
    """
    cliente_clean = str(cliente).replace(";", "")

    # Group providers by renglon number, preserving first-appearance order.
    # This merges duplicate renglones that appear in multiple chunks due to
    # page overlap — same provider in two chunks keeps the first value.
    renglon_providers: dict = {}
    renglon_order: list = []

    for idx, renglon_data in enumerate(all_data.get("renglones", []), start=1):
        renglon = renglon_data.get("renglon", "")
        if not renglon or str(renglon).strip() == "":
            renglon = idx

        proveedores_precios: dict = renglon_data.get("proveedores_precios", {})
        if not proveedores_precios:
            continue

        if renglon not in renglon_providers:
            renglon_providers[renglon] = {}
            renglon_order.append(renglon)

        for proveedor, datos in proveedores_precios.items():
            if proveedor not in renglon_providers[renglon]:
                renglon_providers[renglon][proveedor] = datos

    rows: list[dict] = []

    for renglon in renglon_order:
        proveedores_precios = renglon_providers[renglon]

        # Parse and validate each provider's price.
        # Supports both new format {"precio": "12.50", "marca": "BRAND"} and
        # legacy format where the value is a plain price string "12.50".
        provider_price_list: list[tuple[str, str, str, float]] = []
        for proveedor, datos in proveedores_precios.items():
            if isinstance(datos, dict):
                precio_raw = datos.get("precio", "")
                marca_proveedor = str(datos.get("marca", "")).replace(";", "")
            else:
                precio_raw = datos
                marca_proveedor = ""

            precio_limpio = _limpiar_precio(str(precio_raw))
            if not precio_limpio:
                continue
            try:
                precio_num = float(precio_limpio)
                provider_price_list.append((proveedor, precio_limpio, marca_proveedor, precio_num))
            except ValueError:
                continue

        if not provider_price_list:
            logger.warning("Renglon %s has no valid prices from any provider, skipping", renglon)
            continue

        provider_price_list.sort(key=lambda x: x[3])
        top_3 = provider_price_list[:3]

        logger.debug("Renglon %s: top 3 providers %s", renglon, [p[0] for p in top_3])

        for proveedor, precio, marca_proveedor, _ in top_3:
            proveedor_clean = str(proveedor).replace(";", "").strip() or "sin proveedor"
            marca_clean = str(marca_proveedor).replace(";", "").strip() or "sin marca"
            rows.append({
                "renglon": renglon,
                "proveedor": proveedor_clean,
                "marca": marca_clean,
                "precio": precio,
                "cliente": cliente_clean,
            })

    logger.info(
        "Filter: %d rows after top-3-per-renglon filter for cliente '%s'",
        len(rows),
        cliente,
    )
    return rows


# ======================
# CSV WRITING
# ======================


def _escribir_csv(rows: list[dict], nombre_base: str, cliente: str) -> Path:
    """Write assembled rows to a CSV file in the output directory.

    Uses semicolon (;) as delimiter and UTF-8 encoding (no BOM).
    Applies nombre_unico() to avoid filename collisions.

    Args:
        rows: List of row dicts from _filtrar_top_3_por_renglon().
        nombre_base: Stem of the original filename (no extension).
        cliente: Client identifier used to select the output subdirectory.

    Returns:
        Path to the written CSV file.
    """
    output_dir = get_output_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=cliente)

    csv_filename = nombre_unico(nombre_base, output_dir, ".csv")
    csv_path = output_dir / csv_filename

    fieldnames = ["renglon", "proveedor", "marca", "precio", "cliente"]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(rows)

    logger.info("CSV written: %s (%d rows)", csv_path, len(rows))
    return csv_path


def _mover_a_procesados(ruta_archivo: Path, nombre_base: str, extension: str, cliente: str) -> Path:
    """Move the original source file to the Procesados directory.

    Args:
        ruta_archivo: Current (temp) path of the source file.
        nombre_base: Stem of the original filename.
        extension: File extension including leading dot (e.g., ".xlsx").
        cliente: Client identifier for the destination subdirectory.

    Returns:
        Path where the file was moved.
    """
    processed_dir = get_processed_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=cliente)

    dest_filename = nombre_unico(nombre_base, processed_dir, extension)
    dest_path = processed_dir / dest_filename

    shutil.move(str(ruta_archivo), str(dest_path))
    logger.info("Moved original to Procesados: %s", dest_path)
    return dest_path


# ======================
# PUBLIC ENTRY POINT
# ======================


def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
    *,
    session_id: Optional[UUID] = None,
) -> Path:
    """Process a price comparison document using optimized single-extraction flow.

    Pipeline:
      1. Parse document to Markdown via parse_document() (parser router).
      2. Compress Markdown to reduce tokens.
      3. Extract cliente from filename via obtener_cliente().
      4. Unified extraction: _extraer_comparativa() in 1 Gemini call.
      5. Filter: _filtrar_top_3_por_renglon() keeps top 3 per item (Python, no API).
      6. Write CSV to output directory.
      7. Move original file to Procesados/ directory.

    API calls: 1 total (unified extraction), regardless of how many providers
    are in the document.

    Args:
        ruta_archivo: Path to the (temp) uploaded file on disk.
        nombre_original: Original filename as provided by the user (optional).
            Used to derive nombre_base, extension, and cliente. Falls back to
            ruta_archivo.name if not provided.

    Returns:
        Path to the generated CSV file.

    Raises:
        NoProvidersDetectedError: If no providers are detected.
        json.JSONDecodeError: If Gemini returns unparseable JSON after retries.
        UnsupportedFormatError: If the file extension is not supported by
            the parser router.
        ParserError: If document parsing fails at the format layer.
    """
    # Lazy import to avoid circular dependency at module load time
    from app.parsers import parse_document  # noqa: PLC0415

    if nombre_original:
        nombre_base = Path(nombre_original).stem
        extension = Path(nombre_original).suffix.lower()
    else:
        nombre_base = ruta_archivo.stem
        extension = ruta_archivo.suffix.lower()

    cliente = obtener_cliente(nombre_base)

    logger.info(
        "Processing comparativa: '%s' | cliente: '%s'",
        nombre_original or ruta_archivo.name,
        cliente,
    )

    # Determine extraction strategy: large PDFs use page-based chunking;
    # everything else uses the markdown-based flow.
    es_pdf = extension == ".pdf"
    usar_page_chunks = False

    if es_pdf:
        try:
            from pypdf import PdfReader  # noqa: PLC0415
            total_pages = len(PdfReader(str(ruta_archivo)).pages)
            usar_page_chunks = total_pages > _PDF_PAGE_THRESHOLD
            logger.info("PDF detected: %d pages (threshold=%d)", total_pages, _PDF_PAGE_THRESHOLD)
        except Exception as exc:
            logger.warning("Could not count PDF pages (%s) — falling back to markdown flow", exc)

    if usar_page_chunks:
        # New flow: split PDF by pages, parse each chunk, merge results
        all_data = _extraer_comparativa_por_paginas(
            ruta_archivo,
            session_id=session_id,
            nombre_base=nombre_base,
            cliente=cliente,
        )
    else:
        # Existing flow: parse full document to Markdown, chunk if too large
        markdown = parse_document(ruta_archivo)
        logger.info("Document parsed to Markdown (%d chars)", len(markdown))

        _guardar_docling_output(markdown, nombre_base, cliente)
        markdown = _comprimir_markdown(markdown)
        all_data = _extraer_comparativa(markdown, ruta_archivo, session_id=session_id)

    if not all_data.get("renglones"):
        raise json.JSONDecodeError(
            "No items could be extracted from document",
            "",
            0,
        )

    # 4. Filter: keep only top 3 per renglon (Python, no API call)
    rows = _filtrar_top_3_por_renglon(all_data, cliente)

    if not rows:
        raise json.JSONDecodeError(
            "No valid data after filtering top 3 per item",
            "",
            0,
        )

    # 5. Write CSV
    csv_path = _escribir_csv(rows, nombre_base, cliente)

    # 6. Move original to Procesados
    _mover_a_procesados(ruta_archivo, nombre_base, extension, cliente)

    return csv_path
