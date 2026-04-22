"""
Parser Router: app/parsers.py

Single public entry point: parse_document(filepath) -> str

Routes any supported document format to the appropriate private parser.
All handlers return a UTF-8 string with Unix line endings.

Supported formats:
  .xlsx / .xls  -> _parse_excel()  (pandas + openpyxl/xlrd)
  .ods          -> _parse_ods()    (pandas + odf engine)
  .pdf          -> _parse_pdf()    (docling, fallback to Gemini Vision)
  .html / .htm  -> _parse_html()   (docling or BeautifulSoup4)
  .jpg / .jpeg / .png / .tiff / .tif -> _parse_image() (Gemini Vision)

Anything else raises UnsupportedFormatError.
"""

import logging
import re
from pathlib import Path
from typing import Callable

import pandas as pd
from bs4 import BeautifulSoup

from app.config import CLIENT, MODEL_NAME

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional docling import — guarded so Windows install failures are tolerated
# ---------------------------------------------------------------------------
try:
    import docling_core  # noqa: F401
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.warning(
        "docling not installed. PDFs will be processed via Gemini Vision fallback."
    )

# ---------------------------------------------------------------------------
# Vision prompt (exact text per spec)
# ---------------------------------------------------------------------------
_VISION_PROMPT = (
    "Extract all text from this document. "
    "Preserve table structure as Markdown tables. "
    "Return only the extracted text with no additional commentary."
)

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class UnsupportedFormatError(ValueError):
    """Raised when the file extension is not in the supported set."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"Unsupported file format: '{extension}'")


class ParserError(RuntimeError):
    """Raised when document parsing fails due to a system-level error.

    Wraps the original exception with context about which file failed.
    """

    def __init__(self, filepath: Path, cause: Exception):
        self.filepath = filepath
        self.cause = cause
        super().__init__(f"Failed to parse '{filepath.name}': {cause}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _docling_convert(filepath: Path):
    """Encapsulate docling API call.

    Returns a conversion result object with a .document attribute.
    Isolated here so the docling version-specific API is easy to swap.

    Args:
        filepath: Path to the file to convert.

    Returns:
        A docling conversion result with .document attribute.
    """
    from docling.document_converter import DocumentConverter  # noqa: PLC0415
    converter = DocumentConverter()
    return converter.convert(str(filepath))


def _is_scanned_pdf(text: str, page_count: int, threshold: int = 50) -> bool:
    """Heuristic to classify a PDF as scanned based on text density.

    Args:
        text: Extracted text from docling.
        page_count: Number of pages in the PDF.
        threshold: Minimum average characters per page to be considered native.
            Default is 50 (per spec).

    Returns:
        True if the PDF is likely scanned (below threshold), False otherwise.
    """
    avg_chars = len(text) / max(1, page_count)
    return avg_chars < threshold


# ---------------------------------------------------------------------------
# Private parsers
# ---------------------------------------------------------------------------


def _parse_excel(filepath: Path) -> str:
    """Parse an Excel file (.xlsx or .xls) to a Markdown table.

    Uses openpyxl engine for .xlsx, xlrd for .xls. Reads with header=None
    to preserve raw document structure. NaN values are replaced with empty
    strings before rendering.

    Args:
        filepath: Path to the Excel file.

    Returns:
        Markdown table string. Empty string "" if the DataFrame has 0 rows.

    Side effects:
        Reads file from disk (read-only).
    """
    engine = "xlrd" if filepath.suffix.lower() == ".xls" else "openpyxl"
    df = pd.read_excel(filepath, engine=engine, header=None)

    if df.empty:
        logger.info("Parsed Excel file: %s (empty)", filepath.name)
        return ""

    df = df.fillna("")
    markdown = df.to_markdown(index=False)

    logger.info(
        "Parsed Excel file: %s (%d rows, %d columns)",
        filepath.name,
        df.shape[0],
        df.shape[1],
    )
    return markdown


def _parse_ods(filepath: Path) -> str:
    """Parse an ODS spreadsheet to a Markdown table.

    Uses the odf engine via pandas. Same behavior as _parse_excel but
    for OpenDocument Spreadsheet format. Reads with header=None to preserve
    raw document structure. NaN values are replaced with empty strings.

    Args:
        filepath: Path to the .ods file.

    Returns:
        Markdown table string. Empty string "" if the DataFrame has 0 rows.

    Side effects:
        Reads file from disk (read-only).
    """
    df = pd.read_excel(filepath, engine="odf", header=None)

    if df.empty:
        logger.info("Parsed ODS file: %s (empty)", filepath.name)
        return ""

    df = df.fillna("")
    markdown = df.to_markdown(index=False)

    logger.info(
        "Parsed ODS file: %s (%d rows, %d columns)",
        filepath.name,
        df.shape[0],
        df.shape[1],
    )
    return markdown


def _parse_pdf(filepath: Path) -> str:
    """Parse a PDF file to Markdown.

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
    if not DOCLING_AVAILABLE:
        logger.warning(
            "docling not available, routing PDF to Gemini Vision: %s", filepath.name
        )
        return _parse_image(filepath)

    try:
        result = _docling_convert(filepath)
        text = result.document.export_to_markdown()
        page_count = result.document.num_pages()

        if _is_scanned_pdf(text, page_count):
            logger.info(
                "PDF classified as scanned (low text density), "
                "falling back to Vision: %s",
                filepath.name,
            )
            return _parse_image(filepath)

        logger.info(
            "Parsed native PDF: %s (%d pages, %d chars)",
            filepath.name,
            page_count,
            len(text),
        )
        return text

    except Exception as exc:
        logger.warning(
            "docling failed for %s, falling back to Vision: %s",
            filepath.name,
            exc,
        )
        return _parse_image(filepath)


def _parse_html(filepath: Path) -> str:
    """Parse an HTML file to clean text or Markdown.

    Attempts docling HTML-to-Markdown conversion first. If docling is not
    installed or raises, falls back to BeautifulSoup4: extracts text, strips
    whitespace per line, collapses consecutive blank lines to one.

    Args:
        filepath: Path to the .html or .htm file.

    Returns:
        Clean text string (no HTML tags).

    Side effects:
        Reads file from disk. Encoding errors handled with 'replace' mode.
    """
    if DOCLING_AVAILABLE:
        try:
            result = _docling_convert(filepath)
            text = result.document.export_to_markdown()
            logger.info(
                "Parsed HTML via docling: %s (%d chars)", filepath.name, len(text)
            )
            return text
        except Exception as exc:
            logger.warning(
                "docling HTML conversion failed for %s, using BS4: %s",
                filepath.name,
                exc,
            )

    # BeautifulSoup4 fallback
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_html = f.read()

    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove script and style tags
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Strip per line, collapse consecutive blank lines to one
    lines = [line.strip() for line in text.splitlines()]
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    clean_text = result.strip()

    logger.info(
        "Parsed HTML via BeautifulSoup4: %s (%d chars)", filepath.name, len(clean_text)
    )
    return clean_text


def _parse_image(filepath: Path) -> str:
    """Parse an image or scanned document via Gemini Vision.

    Uploads the file to Gemini's file store, sends it with a text extraction
    prompt, and returns the extracted text. The uploaded file is always deleted
    from Gemini storage in a finally block.

    Retries once on any exception during extraction (total: 2 attempts).
    The finally block runs on each attempt so files are cleaned up per-attempt.

    Args:
        filepath: Path to the image or scanned PDF file.

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
    last_exception = None

    for attempt in range(2):  # 2 total attempts
        uploaded_file = None
        try:
            logger.info(
                "Uploading to Gemini Vision (attempt %d): %s",
                attempt + 1,
                filepath.name,
            )
            uploaded_file = CLIENT.files.upload(file=str(filepath))
            response = CLIENT.models.generate_content(model=MODEL_NAME, contents=[_VISION_PROMPT, uploaded_file])
            text = response.text.strip()
            logger.info(
                "Extracted text from %s via Gemini Vision (%d chars)",
                filepath.name,
                len(text),
            )
            return text

        except Exception as exc:
            last_exception = exc
            if attempt == 0:
                logger.warning(
                    "Vision extraction failed (attempt 1), retrying: %s", exc
                )

        finally:
            if uploaded_file is not None:
                try:
                    CLIENT.files.delete(name=uploaded_file.name)
                    logger.debug(
                        "Deleted Gemini file: %s", uploaded_file.name
                    )
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to delete Gemini file %s: %s",
                        uploaded_file.name,
                        cleanup_exc,
                    )

    raise last_exception


# ---------------------------------------------------------------------------
# Extension router table
# ---------------------------------------------------------------------------

_EXTENSION_ROUTER: dict[str, Callable[[Path], str]] = {
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

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_document(filepath: Path) -> str:
    """Parse a document of any supported format to Markdown.

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
            fails. The original exception is chained via ``raise ... from cause``.

    Side effects:
        - For images/scanned PDFs: uploads to Gemini API via genai.upload_file(),
          then deletes via genai.delete_file() in a finally block.
        - Reads the file from disk (read-only).
        - No temp files created by this function.

    Guarantees:
        - Always returns a Python str (UTF-8 in-memory).
        - Line endings are \\n (Unix style).
        - No Gemini uploaded files left in storage (cleanup in finally).
        - No NaN or "nan" strings in spreadsheet output (replaced with "").
    """
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = filepath.suffix.lower()
    handler = _EXTENSION_ROUTER.get(ext)

    if handler is None:
        raise UnsupportedFormatError(ext)

    logger.info("Parsing document: %s (format: %s)", filepath.name, ext)

    try:
        result = handler(filepath)
    except (UnsupportedFormatError, ParserError):
        raise
    except Exception as exc:
        raise ParserError(filepath, exc) from exc

    # Normalize line endings to Unix style
    result = result.replace("\r\n", "\n")

    logger.info("Successfully parsed: %s", filepath.name)
    return result
