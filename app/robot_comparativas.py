"""
Comparativas extraction pipeline: app/robot_comparativas.py

Extracts price comparison documents using Gemini with automatic chunking for
large files (> _CHUNK_THRESHOLD chars):
  1. Parse document to Markdown, compress to reduce tokens.
  2. If small: single Gemini call. If large: split into chunks of _CHUNK_SIZE
     renglones each, call Gemini per chunk, merge results.
  3. Filter: Keep only top 3 providers per renglon (Python, no API call).

Public API (signature unchanged from prior version):
  procesar_comparativa(ruta_archivo, nombre_original) -> Path

Custom Exceptions:
  NoProvidersDetectedError  -- No providers detected in the document.
"""

import csv
import json
import logging
import re
import shutil
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
- Return ALL items found"""

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


# ======================
# HELPERS
# ======================


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
        if result and isinstance(result[0], dict) and "renglon" in result[0]:
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

    # Handle Argentine/European format: "1.234,56" (dot thousands, comma decimal)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    # Handle comma-only decimal: "12,34"
    elif "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    # else: dot-only format "1234.56" or "1234567" — no change needed

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
    processes each half independently, and merges the results.
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
        r1 = _llamar_gemini_json(prompt, sub_chunks[0])
        r2 = _llamar_gemini_json(prompt, sub_chunks[1])
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
                logger.error("Chunk %d/%d falló definitivamente: %s", idx + 1, total, exc)
                results[idx] = {"proveedores": [], "renglones": []}

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

    logger.info(
        "Detected %d providers in '%s': %s", len(providers), filepath.name, providers,
    )
    logger.info("Total renglones extracted: %d from %d chunks", len(all_renglones), total)
    return {"proveedores": providers, "renglones": all_renglones}



def _filtrar_top_3_por_renglon(all_data: dict, cliente: str) -> list[dict]:
    """Filter extracted data to keep only top 3 providers per renglon by price.

    Parses and normalizes all prices using _limpiar_precio(), sorts by
    numeric value (lowest first), and keeps at most 3 providers per item.
    Items with no valid prices are logged and skipped.

    Args:
        all_data: Dict returned by _extraer_todos_con_precios().
        cliente: Client name derived from the filename.

    Returns:
        List of row dicts with keys: renglon, proveedor, marca,
        precio, cliente — ready for csv.DictWriter. Contains at most 3 rows
        per renglon, ordered by ascending price.
    """
    rows: list[dict] = []
    cliente_clean = str(cliente).replace(";", "")

    for idx, renglon_data in enumerate(all_data.get("renglones", []), start=1):
        renglon = renglon_data.get("renglon", "")
        # Si no viene el renglon, generar número incremental
        if not renglon or str(renglon).strip() == "":
            renglon = idx
        proveedores_precios: dict = renglon_data.get("proveedores_precios", {})

        if not proveedores_precios:
            logger.warning("Renglon %s has no provider prices, skipping", renglon)
            continue

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

        # Sort by numeric price ascending, keep top 3
        provider_price_list.sort(key=lambda x: x[3])
        top_3 = provider_price_list[:3]

        logger.debug(
            "Renglon %s: top 3 providers %s",
            renglon,
            [p[0] for p in top_3],
        )

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

    # 1. Parse document to Markdown
    markdown = parse_document(ruta_archivo)
    logger.info("Document parsed to Markdown (%d chars)", len(markdown))

    # 1.5 Save docling output before compression
    _guardar_docling_output(markdown, nombre_base, cliente)

    # 2. Compress Markdown (Fase 2: reduce tokens)
    markdown = _comprimir_markdown(markdown)

    # 3. Extraccion unificada: detecta proveedores + extrae precios (con chunking si aplica)
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
