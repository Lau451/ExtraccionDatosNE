"""
Orden de compra extraction pipeline: services/extraccion/robot_orden_compra.py

Extracts client purchase-order documents (PDF/imagen/Excel/HTML) via a single
Gemini JSON call. Order documents are short (one client, N line items) — unlike
robot_comparativas.py, no page/chunk splitting is needed here.

Public API (misma firma y estructura que procesar_comparativa):
  procesar_orden_compra(ruta_archivo, nombre_original, *, session_id=None,
                         instrucciones_extra=None) -> Path

CSV grammar (D6, openspec/changes/orden-compra/design.md § D6):
  numero_oc;fecha_emision;cuit_cliente;razon_social_cliente;direccion_entrega;
  cantidad_entregas;numero_renglon;descripcion;cantidad;precio_unitario;entregas

Regla dura (C10, D6): `numero_renglon` NUNCA se fabrica. Si el documento no
declara número de línea para un renglón, la celda queda vacía — el prompt lo
prohíbe explícitamente y `_construir_filas()` nunca lo deriva ni autoincrementa.

Custom Exceptions:
  OrdenCompraSinRenglonesError -- No se detectó ningún renglón en el documento.
"""

import csv
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from google.genai import types

from services.extraccion.config import get_next_client, get_output_dir, get_processed_dir, generate_with_fallback
from services.extraccion.robot import obtener_cliente, nombre_unico
from services.extraccion.gemini_errors import handle_gemini_errors, GeminiTruncationError
from services.extraccion.parsers import parse_document

logger = logging.getLogger(__name__)

_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    max_output_tokens=65_536,
)

# Orden de columnas del CSV — D6. No reordenar: main.py y la lectura de
# presupuestacion/extraccion/ asumen este orden exacto.
_FIELDNAMES = [
    "numero_oc",
    "fecha_emision",
    "cuit_cliente",
    "razon_social_cliente",
    "direccion_entrega",
    "cantidad_entregas",
    "numero_renglon",
    "descripcion",
    "cantidad",
    "precio_unitario",
    "entregas",
]

# ======================
# PROMPT
# ======================

_PROMPT = """Extract data from this purchase order document (orden de compra) issued by a CLIENT.

This document is written by the CUSTOMER (not by us) to order products from a supplier.
It has a header with order-level data, and a list of line items (renglones).

Return ONLY valid JSON with this exact structure:
{
  "numero_oc": "the order number as declared, e.g. OC-4471",
  "fecha_emision": "issue date normalized to DD/MM/AAAA, or empty string if not found",
  "cuit_cliente": "the customer's CUIT — digits ONLY, no dashes/dots/spaces (11 digits), or empty string if not found",
  "razon_social_cliente": "the customer's legal/business name as written, or empty string",
  "direccion_entrega": "delivery address as written, or empty string",
  "cantidad_entregas": "how many deliveries the document declares in total (a plain number), or empty string if not stated",
  "renglones": [
    {
      "numero_renglon": "the line number EXACTLY as declared in the document, or empty string — see CRITICAL RULE below",
      "descripcion": "product description for this line",
      "cantidad": "quantity ordered for this line (a plain number)",
      "precio_unitario": "unit price for this line, numeric, WITHOUT any thousands-separator — keep only the single decimal separator exactly as the document uses it (comma or dot). Example: document shows '$1.250,00' -> output '1250,00'. Document shows '980,50' -> output '980,50'. Empty string if not found.",
      "entregas": "delivery breakdown for THIS line only, formatted as cantidad@plazo_dias pairs separated by '|' (e.g. '50@30|50@60' = 50 units at 30 days, 50 units at 60 days). Empty string if the document does not break this line down by delivery."
    }
  ]
}

CRITICAL RULE ABOUT LINE NUMBERS (numero_renglon) — READ CAREFULLY:
- If the document explicitly numbers each line item (a "Renglón"/"Item"/"N°" column or similar),
  copy that number EXACTLY as it appears, as a string.
- If the document does NOT number its line items in ANY way, leave "numero_renglon" as an
  EMPTY STRING for every line.
- You are STRICTLY FORBIDDEN from inventing, deriving, auto-incrementing, or inferring a line
  number from the order of appearance in the document or in your output. A fabricated number is
  indistinguishable from a real one and would mislead the operator who reviews it later.
- An empty numero_renglon is a VALID, EXPECTED result for some documents. Never fail, refuse to
  extract, or fill it in just because it is empty.

RULES FOR THE DELIVERY BREAKDOWN (entregas):
- Only build a "cantidad@plazo_dias" pair when the document explicitly states a quantity AND a
  number of days (or an equivalent date you can convert to days from the issue date) for that
  specific line.
- Use "|" to separate multiple deliveries for the same line, in the order they are declared.
- plazo_dias must be a plain non-negative integer. cantidad may have a decimal separator (. or ,)
  if the document shows one.
- If a line has a single, undivided delivery (no explicit per-line breakdown), leave "entregas"
  as an empty string — do not invent a single-entry breakdown.

GENERAL RULES:
- Never invent data. Any field not found in the document is an empty string ("").
- "cantidad_entregas" reflects what the document states about the ORDER as a whole; it is
  independent from how many "entregas" pairs any single line declares.
- Return ALL line items found, in the order they appear in the document."""


# ======================
# CUSTOM EXCEPTIONS
# ======================


class OrdenCompraSinRenglonesError(ValueError):
    """Raised when no line items (renglones) could be extracted from the document.

    Same principle as NoProvidersDetectedError in robot_comparativas.py: a CSV
    with zero data rows is not a valid extraction result, so this fails loudly
    instead of silently writing an empty file.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# ======================
# GEMINI CALL
# ======================


@handle_gemini_errors(max_retries=4, backoff_factor=40.0)
def _llamar_gemini_orden_compra(markdown: str, *, prompt: str = _PROMPT) -> dict[str, Any]:
    """Call Gemini with response_mime_type='application/json' for guaranteed valid JSON.

    Mirrors robot_comparativas._llamar_gemini_json: checks finish_reason BEFORE
    parsing to detect truncation early, raises GeminiTruncationError (not a JSON
    parse error) so the retry decorator's backoff applies uniformly.

    Raises:
        GeminiTruncationError: Response truncated (MAX_TOKENS) or invalid JSON.
        GeminiQuotaExceededError / GeminiRateLimitError: propagated by the decorator.
    """
    client = get_next_client()
    response = generate_with_fallback(client, f"{prompt}\n\n{markdown}", config=_JSON_CONFIG)

    finish_reason = None
    if response.candidates:
        finish_reason = str(response.candidates[0].finish_reason)

    logger.info(
        "Gemini response (orden_compra): %d chars, finish_reason=%s",
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

    if not isinstance(result, dict):
        logger.warning("Respuesta de orden_compra no es un dict (%s) — se trata como vacía", type(result))
        return {"renglones": []}

    return result


# ======================
# TRANSFORMACIÓN (pura)
# ======================


def _construir_filas(datos: dict[str, Any]) -> list[dict[str, str]]:
    """Convierte el JSON de Gemini en filas listas para csv.DictWriter (D6).

    Función pura: sin I/O, sin llamadas a Gemini. Repite los campos de cabecera
    en cada fila (D6: "una fila por renglón, los campos de cabecera se repiten
    en cada fila"). `numero_renglon` se preserva tal cual llegó — nunca se
    autoincrementa ni se deriva del orden de aparición (C10).

    Args:
        datos: dict con las claves de cabecera + "renglones": list[dict].

    Returns:
        Lista de dicts con las claves de _FIELDNAMES, en ese orden lógico
        (el orden real en el CSV lo fija csv.DictWriter con fieldnames=_FIELDNAMES).
    """
    cabecera = {
        "numero_oc": str(datos.get("numero_oc") or "").strip(),
        "fecha_emision": str(datos.get("fecha_emision") or "").strip(),
        "cuit_cliente": str(datos.get("cuit_cliente") or "").strip(),
        "razon_social_cliente": str(datos.get("razon_social_cliente") or "").strip(),
        "direccion_entrega": str(datos.get("direccion_entrega") or "").strip(),
        "cantidad_entregas": str(datos.get("cantidad_entregas") or "").strip(),
    }

    filas: list[dict[str, str]] = []
    for renglon in datos.get("renglones") or []:
        fila = dict(cabecera)
        fila["numero_renglon"] = str(renglon.get("numero_renglon") or "").strip()
        fila["descripcion"] = str(renglon.get("descripcion") or "").strip()
        fila["cantidad"] = str(renglon.get("cantidad") or "").strip()
        fila["precio_unitario"] = str(renglon.get("precio_unitario") or "").strip()
        fila["entregas"] = str(renglon.get("entregas") or "").strip()
        filas.append(fila)

    return filas


# ======================
# CSV WRITING
# ======================


def _escribir_csv(rows: list[dict[str, str]], nombre_base: str, cliente: str) -> Path:
    """Write assembled rows to a CSV file in the output directory.

    Uses semicolon (;) as delimiter, UTF-8 encoding (no BOM) and QUOTE_MINIMAL —
    idéntico a robot_comparativas.py:850-859 / D6.

    Args:
        rows: List of row dicts from _construir_filas().
        nombre_base: Stem of the original filename (no extension).
        cliente: Client identifier used to select the output subdirectory.

    Returns:
        Path to the written CSV file.
    """
    output_dir = get_output_dir(origen_id=cliente)

    csv_filename = nombre_unico(nombre_base, output_dir, ".csv")
    csv_path = output_dir / csv_filename

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=_FIELDNAMES,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(rows)

    logger.info("CSV written (orden_compra): %s (%d rows)", csv_path, len(rows))
    return csv_path


def _mover_a_procesados(ruta_archivo: Path, nombre_base: str, extension: str, cliente: str) -> Path:
    """Move the original source file to the Procesados directory.

    Idéntico en estructura a robot_comparativas._mover_a_procesados.
    """
    processed_dir = get_processed_dir(origen_id=cliente)

    dest_filename = nombre_unico(nombre_base, processed_dir, extension)
    dest_path = processed_dir / dest_filename

    shutil.move(str(ruta_archivo), str(dest_path))
    logger.info("Moved original to Procesados: %s", dest_path)
    return dest_path


# ======================
# PUBLIC ENTRY POINT
# ======================


def procesar_orden_compra(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
    *,
    session_id: Optional[UUID] = None,
    instrucciones_extra: Optional[str] = None,  # §8: formato por cliente, ver v_formato_para_prompt
) -> Path:
    """Process a client purchase-order document into a flat D6 CSV.

    Pipeline:
      1. Parse document to Markdown via parse_document() (parser router, sin cambios).
      2. Single Gemini JSON call: cabecera + renglones (_llamar_gemini_orden_compra).
      3. Transform: _construir_filas() (pura) repite cabecera por renglón, preserva
         numero_renglon tal cual (nunca lo fabrica — C10).
      4. Write CSV to output directory (D6 grammar, ';' / UTF-8 / QUOTE_MINIMAL).
      5. Move original file to Procesados/ directory.

    Args:
        ruta_archivo: Path to the (temp) uploaded file on disk.
        nombre_original: Original filename as provided by the user (optional).
            Used to derive nombre_base, extension, and cliente. Falls back to
            ruta_archivo.name if not provided.
        session_id: Reservado para persistencia de sesión (no usado en esta función).
        instrucciones_extra: §8 — instrucciones específicas de cliente, inyectadas
            al final del prompt si vienen.

    Returns:
        Path to the generated CSV file.

    Raises:
        OrdenCompraSinRenglonesError: If no line items are detected.
        json.JSONDecodeError / GeminiTruncationError: Propagated from Gemini call
            after retries (ver gemini_errors.handle_gemini_errors).
        UnsupportedFormatError / ParserError: Propagadas por parse_document().
    """
    if nombre_original:
        nombre_base = Path(nombre_original).stem
        extension = Path(nombre_original).suffix.lower()
    else:
        nombre_base = ruta_archivo.stem
        extension = ruta_archivo.suffix.lower()

    cliente = obtener_cliente(nombre_base)

    logger.info(
        "Processing orden_compra: '%s' | cliente: '%s'",
        nombre_original or ruta_archivo.name,
        cliente,
    )

    markdown = parse_document(ruta_archivo)
    logger.info("Document parsed to Markdown (%d chars)", len(markdown))

    prompt_efectivo = (
        f"{_PROMPT}\n\nINSTRUCCIONES ESPECIFICAS DE ESTE CLIENTE:\n{instrucciones_extra}\n"
        if instrucciones_extra
        else _PROMPT
    )

    datos = _llamar_gemini_orden_compra(markdown, prompt=prompt_efectivo)

    if not datos.get("renglones"):
        raise OrdenCompraSinRenglonesError(
            f"No se detectaron renglones en el documento '{ruta_archivo.name}'. "
            "El documento puede no ser una orden de compra válida, o el formato es irreconocible."
        )

    rows = _construir_filas(datos)

    if not rows:
        raise OrdenCompraSinRenglonesError(
            f"No se pudo construir ninguna fila a partir del documento '{ruta_archivo.name}'."
        )

    csv_path = _escribir_csv(rows, nombre_base, cliente)

    _mover_a_procesados(ruta_archivo, nombre_base, extension, cliente)

    return csv_path
