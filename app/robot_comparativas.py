"""
Comparativas extraction pipeline: app/robot_comparativas.py

Two-step Gemini extraction for price comparison documents:
  Step 1: Detect all providers/suppliers in the document.
  Step 2: Extract structured data per provider.

Public API (signature unchanged from prior version):
  procesar_comparativa(ruta_archivo, nombre_original) -> Path

Custom Exceptions:
  NoProvidersDetectedError  -- Step 1 returned an empty provider list.
"""

import csv
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from app.config import MODEL, get_output_dir, get_processed_dir, COMPARATIVAS_OUTPUT_BASE
from app.robot import obtener_cliente, nombre_unico

logger = logging.getLogger(__name__)

# ======================
# PROMPTS
# ======================

_PROMPT_DETECT_PROVIDERS = """Analyze this price comparison document and identify ALL providers/suppliers.

Return ONLY a valid JSON object with no additional text.
If no providers are found, return {"proveedores": []}.

{"proveedores": ["Provider Name 1", "Provider Name 2", ...]}"""

_PROMPT_EXTRACT_PROVIDER = """Extract ONLY the data for provider: {proveedor}

Return ONLY a valid JSON object with no additional text.
{{
  "proveedor": "{proveedor}",
  "renglones": [
    {{
      "renglon": <number or order>,
      "descripcion": "<item description>",
      "marca": "<brand name or empty string>",
      "precio": "<numeric price as string or empty string>"
    }}
  ]
}}"""

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


def _llamar_gemini_json(prompt: str, markdown: str, max_retries: int = 2) -> dict:
    """Call Gemini expecting a JSON response, with retry on parse failure.

    Strips Markdown code fences (```json ... ```) before parsing.
    Retries up to max_retries times on JSONDecodeError, logging a WARNING
    each time. On final failure, logs an ERROR and re-raises the
    JSONDecodeError.

    Args:
        prompt: The prompt text to send to Gemini.
        markdown: The document content (Markdown) appended after the prompt.
        max_retries: Number of additional attempts after the first (default 2,
            meaning up to 3 total attempts).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        json.JSONDecodeError: If JSON parsing fails after all retries.
    """
    last_error: Optional[json.JSONDecodeError] = None
    text: str = ""

    for attempt in range(max_retries + 1):
        response = MODEL.generate_content(f"{prompt}\n\n{markdown}")
        text = response.text.strip()

        # Strip Markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    "JSON parse failed (attempt %d/%d), retrying... Error: %s",
                    attempt + 1,
                    max_retries + 1,
                    str(e)[:100],
                )

    logger.error(
        "Failed to parse JSON after %d attempts. Last response: %s",
        max_retries + 1,
        text[:200],
    )
    raise last_error  # type: ignore[misc]


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


# ======================
# PIPELINE STEPS
# ======================


def _detectar_proveedores(markdown: str, filepath: Path) -> list[str]:
    """Step 1: Detect all providers/suppliers in the document.

    Sends the full Markdown to Gemini with a structured JSON prompt.
    Parses the response and returns the list of provider name strings.

    Args:
        markdown: Full document content as a Markdown string.
        filepath: Original file path — used only in the error message.

    Returns:
        List of provider name strings (non-empty).

    Raises:
        NoProvidersDetectedError: If the parsed JSON has an empty providers list.
        json.JSONDecodeError: If Gemini returns unparseable JSON after all retries.
    """
    result = _llamar_gemini_json(_PROMPT_DETECT_PROVIDERS, markdown)
    providers: list[str] = result.get("proveedores", [])

    logger.info(
        "Step 1: Detected %d providers in '%s': %s",
        len(providers),
        filepath.name,
        providers,
    )

    if not providers:
        raise NoProvidersDetectedError(
            f"No providers detected in document '{filepath.name}'. "
            "The document may not be a valid price comparison, or the format is unrecognized."
        )

    return providers


def _extraer_datos_proveedor(markdown: str, proveedor: str) -> dict:
    """Step 2: Extract structured data for a single provider.

    Sends the full Markdown plus the provider name to Gemini with a
    structured JSON prompt requesting all line items for that provider.

    Args:
        markdown: Full document content as a Markdown string.
        proveedor: Provider name to extract data for.

    Returns:
        Dict with keys "proveedor" (str) and "renglones" (list[dict]).
        Each renglon dict has: "renglon", "descripcion", "marca", "precio".
        Returns {"proveedor": proveedor, "renglones": []} if no rows found.
    """
    prompt = _PROMPT_EXTRACT_PROVIDER.format(proveedor=proveedor)
    result = _llamar_gemini_json(prompt, markdown)

    renglones = result.get("renglones", [])
    logger.info(
        "Step 2: Extracted %d renglones for provider '%s'",
        len(renglones),
        proveedor,
    )

    return result


def _ensamblar_csv(providers_data: list[dict], cliente: str) -> list[dict]:
    """Merge per-provider extracted data into final CSV rows.

    Applies _limpiar_precio() to every precio value. Strips semicolons from
    all text fields (delimiter collision prevention). Handles missing "marca"
    field (defaults to empty string). Filters fully empty rows (no
    descripcion, no marca, no precio).

    Args:
        providers_data: List of dicts returned by _extraer_datos_proveedor().
        cliente: Client/origin name extracted from the filename.

    Returns:
        List of dicts with keys: renglon, descripcion, proveedor, marca,
        precio, cliente — ready for csv.DictWriter.
    """
    rows: list[dict] = []
    auto_renglon = 1

    for provider_result in providers_data:
        proveedor = str(provider_result.get("proveedor", "")).replace(";", "")
        renglones = provider_result.get("renglones", [])

        for renglon_data in renglones:
            # Renglon numbering: use value from Gemini if it's a positive int,
            # otherwise fall back to sequential auto-numbering.
            raw_renglon = renglon_data.get("renglon", "")
            try:
                renglon_val = int(raw_renglon)
                if renglon_val <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                renglon_val = auto_renglon

            auto_renglon += 1

            descripcion = str(renglon_data.get("descripcion", "")).replace(";", "")
            marca = str(renglon_data.get("marca", "")).replace(";", "")
            precio = _limpiar_precio(str(renglon_data.get("precio", "")))
            cliente_clean = str(cliente).replace(";", "")

            # Skip fully empty rows (spec: no descripcion + no marca + no precio)
            if not descripcion and not marca and not precio:
                continue

            row = {
                "renglon": renglon_val,
                "descripcion": descripcion,
                "proveedor": proveedor,
                "marca": marca,
                "precio": precio,
                "cliente": cliente_clean,
            }
            rows.append(row)

    logger.info(
        "Assembly: merged %d providers into %d CSV rows for cliente '%s'",
        len(providers_data),
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
        rows: List of row dicts from _ensamblar_csv().
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
) -> Path:
    """Process a price comparison document using two-step Gemini extraction.

    Pipeline:
      1. Parse document to Markdown via parse_document() (parser router).
      2. Extract cliente from filename via obtener_cliente().
      3. Step 1 — Detect providers: _detectar_proveedores(markdown, filepath).
      4. Step 2 — Extract per provider: _extraer_datos_proveedor() for each.
         Failed providers are logged and skipped (partial failure is allowed).
      5. Assembly: _ensamblar_csv() merges all results and adds cliente field.
      6. Write CSV to output directory.
      7. Move original file to Procesados/ directory.

    Args:
        ruta_archivo: Path to the (temp) uploaded file on disk.
        nombre_original: Original filename as provided by the user (optional).
            Used to derive nombre_base, extension, and cliente. Falls back to
            ruta_archivo.name if not provided.

    Returns:
        Path to the generated CSV file.

    Raises:
        NoProvidersDetectedError: If no providers are detected in Step 1.
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

    # 2. Step 1: Detect providers
    providers = _detectar_proveedores(markdown, ruta_archivo)

    # 3. Step 2: Extract per provider (sequential, partial failure allowed)
    providers_data: list[dict] = []
    for proveedor in providers:
        try:
            data = _extraer_datos_proveedor(markdown, proveedor)
            providers_data.append(data)
        except Exception as e:
            logger.error(
                "Failed to extract data for provider '%s', skipping: %s",
                proveedor,
                e,
            )
            # Partial failure: continue with remaining providers

    if not providers_data:
        # All providers failed extraction — nothing to write
        raise json.JSONDecodeError(
            "No provider data could be extracted for any provider",
            "",
            0,
        )

    # 4. Assembly
    rows = _ensamblar_csv(providers_data, cliente)

    # 5. Write CSV
    csv_path = _escribir_csv(rows, nombre_base, cliente)

    # 6. Move original to Procesados
    _mover_a_procesados(ruta_archivo, nombre_base, extension, cliente)

    return csv_path
