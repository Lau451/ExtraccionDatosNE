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
from pathlib import Path
from typing import Optional
from uuid import UUID

from google.genai import types

from app.config import CLIENT, get_output_dir, get_processed_dir, COMPARATIVAS_OUTPUT_BASE, DATA_DIR, get_next_client, generate_with_fallback
from app.robot import obtener_cliente, nombre_unico
from app.gemini_errors import handle_gemini_errors, GeminiQuotaExceededError, GeminiRateLimitError
from app.persistent_chunking import guardar_chunk

logger = logging.getLogger(__name__)

_JSON_CONFIG = types.GenerateContentConfig(response_mime_type="application/json")

_CHUNK_THRESHOLD = 40_000  # chars; above this, use chunked Gemini calls (lowered for robustness)
_CHUNK_SIZE = 20            # max items per Gemini call (conservative to avoid truncation)

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

Return ONLY valid JSON:
{
  "proveedores": ["Provider A", "Provider B"],
  "renglones": [
    {
      "renglon": 1,
      "descripcion": "Full product/medication description — NOT the brand name",
      "proveedores_precios": {
        "Provider A": {"precio": "12.50", "marca": "BRAND_A"},
        "Provider B": {"precio": "", "marca": ""}
      }
    }
  ]
}

RULES:
- "descripcion": product name and dosage only (e.g. "AMOXICILINA 500 MG / 5 ML SUSP X 90 ML"), never include the brand here
- "marca": per-provider brand — extract the brand each provider offers for that item, use empty string if none
- "precio": unit price as a number string, empty string if provider does not quote
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

    Uses structured output to eliminate JSONDecodeError and code fence issues.
    API-level retries are handled by the @handle_gemini_errors decorator.

    Args:
        prompt: The prompt text to send to Gemini.
        markdown: The document content (Markdown) appended after the prompt.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        GeminiQuotaExceededError: If Gemini API quota is exceeded.
        GeminiRateLimitError: If Gemini API rate limit is exceeded.
    """
    client = get_next_client()
    response = generate_with_fallback(client, f"{prompt}\n\n{markdown}", config=_JSON_CONFIG)

    # DEBUG: Log raw response to diagnose JSON issues
    logger.info("Gemini raw response (first 500 chars): %s", response.text[:500])
    logger.info("Gemini response length: %d chars", len(response.text))

    return json.loads(response.text)


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


def _extraer_comparativa(markdown: str, filepath: Path, *, session_id: Optional[UUID] = None) -> dict:
    """Extract providers and all items with prices from a comparativa document.

    Uses a single Gemini call for small documents. For large documents
    (> _CHUNK_THRESHOLD chars) automatically splits into chunks of _CHUNK_SIZE
    renglones each, calls Gemini per chunk, and merges the results. Each chunk
    includes the full Excel header context so provider detection is consistent.

    Args:
        markdown: Compressed document content as a Markdown string.
        filepath: Original file path — used only in error messages.

    Returns:
        Dict with keys "proveedores" (list[str]) and "renglones" (list[dict]).

    Raises:
        NoProvidersDetectedError: If no providers are detected in the first chunk.
    """
    chunks = _split_markdown_chunks(markdown) if len(markdown) > _CHUNK_THRESHOLD else [markdown]

    if len(chunks) > 1:
        logger.info(
            "Large document (%d chars): splitting into %d chunks of ~%d renglones each",
            len(markdown),
            len(chunks),
            _CHUNK_SIZE,
        )

    all_renglones: list[dict] = []
    providers: list[str] = []

    for idx, chunk in enumerate(chunks):
        result = _llamar_gemini_json(_PROMPT_UNIFIED, chunk)

        # Guardar chunk en Supabase si hay session_id activo
        if session_id:
            try:
                guardar_chunk(
                    session_id=session_id,
                    chunk_num=idx,
                    resultado_json=result,
                )
            except Exception as e:
                logger.warning("Error al guardar chunk %d en Supabase: %s", idx, e)

        chunk_providers: list[str] = result.get("proveedores", [])

        if idx == 0:
            if not chunk_providers:
                raise NoProvidersDetectedError(
                    f"No providers detected in document '{filepath.name}'. "
                    "The document may not be a valid price comparison, or the format is unrecognized."
                )
            providers = chunk_providers
            logger.info(
                "Detected %d providers in '%s': %s",
                len(providers),
                filepath.name,
                providers,
            )

        chunk_renglones = result.get("renglones", [])
        all_renglones.extend(chunk_renglones)

        if len(chunks) > 1:
            logger.info(
                "Chunk %d/%d: extracted %d renglones",
                idx + 1,
                len(chunks),
                len(chunk_renglones),
            )

    logger.info("Total renglones extracted: %d", len(all_renglones))
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
        List of row dicts with keys: renglon, descripcion, proveedor, marca,
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
        descripcion = str(renglon_data.get("descripcion", "")).replace(";", "")
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
            logger.warning(
                "Renglon %s (%s) has no valid prices from any provider, skipping",
                renglon,
                descripcion,
            )
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
            rows.append({
                "renglon": renglon,
                "descripcion": descripcion,
                "proveedor": str(proveedor).replace(";", ""),
                "marca": marca_proveedor,
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

    fieldnames = ["renglon", "descripcion", "proveedor", "marca", "precio", "cliente"]

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
