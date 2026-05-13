"""
Parser Router: app/parsers.py

Single public entry point: parse_document(filepath) -> str

Routes any supported document format to the appropriate private parser.
All handlers return a UTF-8 string with Unix line endings.

Supported formats:
  .xlsx / .xls  -> _parse_excel()  (pandas + openpyxl/xlrd)
  .ods          -> _parse_ods()    (pandas + odf engine)
  .pdf          -> _parse_pdf()    (pdfplumber native → Docling lightweight → Vision)
  .html / .htm  -> _parse_html()   (BeautifulSoup4)
  .jpg / .jpeg / .png / .tiff / .tif -> _parse_image() (Gemini Vision)

Anything else raises UnsupportedFormatError.
"""

import gc
import logging
import re
from pathlib import Path
from typing import Callable

import pandas as pd
from bs4 import BeautifulSoup

from app.config import CLIENT, generate_with_fallback

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

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not installed. Scanned PDF detection disabled (assumes native).")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not installed. Native PDF extraction will fall back to Docling.")

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


def _split_pdf_by_pages(filepath: Path, pages_per_chunk: int = 50) -> list[Path]:
    """Split a PDF into smaller chunks by page count.

    Creates temporary PDF files, each containing at most pages_per_chunk pages.
    Temporary chunks are stored in the system temp directory and cleaned up
    after processing (via caller responsibility or context manager).

    Args:
        filepath: Path to the input PDF file.
        pages_per_chunk: Maximum pages per chunk (default 50).

    Returns:
        List of Path objects pointing to temporary chunk PDF files.
        Empty list if the PDF has <= pages_per_chunk pages (no split needed).

    Raises:
        ImportError: If PyPDF is not installed.
        Exception: If PDF reading/writing fails.
    """
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: PLC0415
    except ImportError:
        logger.error("pypdf not installed. Cannot split large PDFs.")
        raise ImportError("pypdf is required for PDF chunking. Install via: pip install pypdf>=4.0.0")

    reader = PdfReader(str(filepath))
    total_pages = len(reader.pages)

    if total_pages <= pages_per_chunk:
        logger.debug("PDF has %d pages, no split needed", total_pages)
        return []

    chunks = []
    import tempfile
    temp_dir = Path(tempfile.gettempdir())

    for i in range(0, total_pages, pages_per_chunk):
        chunk_start = i
        chunk_end = min(i + pages_per_chunk, total_pages)
        chunk_num = i // pages_per_chunk

        writer = PdfWriter()
        for page_num in range(chunk_start, chunk_end):
            writer.add_page(reader.pages[page_num])

        chunk_filename = f"docling_chunk_{filepath.stem}_{chunk_num}.pdf"
        chunk_path = temp_dir / chunk_filename

        with open(chunk_path, "wb") as f:
            writer.write(f)

        chunks.append(chunk_path)
        logger.info(
            "PDF chunk %d: pages %d-%d → %s",
            chunk_num,
            chunk_start + 1,
            chunk_end,
            chunk_path.name,
        )

    logger.info(
        "PDF split: %d pages → %d chunks of ~%d pages",
        total_pages,
        len(chunks),
        pages_per_chunk,
    )
    return chunks


def _docling_convert(filepath: Path, lightweight: bool = False):
    """Encapsulate docling API call.

    Returns a conversion result object with a .document attribute.
    Isolated here so the docling version-specific API is easy to swap.

    Args:
        filepath: Path to the file to convert.
        lightweight: If True, disables page image generation to reduce RAM usage.

    Returns:
        A docling conversion result with .document attribute.
    """
    from docling.document_converter import DocumentConverter  # noqa: PLC0415
    if lightweight:
        try:
            from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
            from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: PLC0415
            from docling.document_converter import PdfFormatOption  # noqa: PLC0415
            pipeline_options = PdfPipelineOptions(generate_page_images=False)
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
        except Exception:
            converter = DocumentConverter()
    else:
        converter = DocumentConverter()
    return converter.convert(str(filepath))


def is_scanned_pdf(path: Path, sample_pages: int = 3) -> bool:
    """Detect scanned PDFs by checking text density BEFORE any heavy processing.

    Uses PyMuPDF to read the native text layer directly — fast and low-memory.
    Returns True if fewer than 50% of sampled pages contain more than 50 chars,
    which indicates the PDF has no embedded text (i.e., it's image-only/scanned).

    Falls back to False (assume native) if PyMuPDF is not installed.
    """
    if not PYMUPDF_AVAILABLE:
        return False
    doc = fitz.open(str(path))
    try:
        pages_to_check = min(sample_pages, len(doc))
        if pages_to_check == 0:
            return False
        text_pages = sum(
            1 for i in range(pages_to_check)
            if len(doc[i].get_text()) > 50
        )
        return (text_pages / pages_to_check) < 0.5
    finally:
        doc.close()


def _merge_fragmented_rows(rows: list[list]) -> list[list]:
    """Merge continuation rows into the preceding row.

    A continuation row has content only in the first cell — all other cells
    are None or empty. This happens when a provider name wraps to the next
    visual line in the source document but belongs to the same table row.
    """
    merged: list[list] = []
    for row in rows:
        first_has_content = row[0] is not None and str(row[0]).strip()
        rest_all_empty = all(c is None or str(c).strip() == "" for c in row[1:])
        if merged and first_has_content and rest_all_empty:
            prev_text = str(merged[-1][0] or '').strip()
            merged[-1][0] = (prev_text + " " + str(row[0]).strip()).strip()
        else:
            merged.append(list(row))
    return merged


def _clean_brand(raw: str) -> str:
    """Strip PM/C. catalog codes and trailing notes from a brand entry.

    Examples:
      "ELEA PM59408"                   -> "ELEA"
      "ELEA PHOENIX PM59408"           -> "ELEA PHOENIX"
      "LEPETIT/LAFEDAR PM48886/44893"  -> "LEPETIT/LAFEDAR"
      "RICHET CAJA X 200"              -> "RICHET"
      "LAFEDAR VTO 07/26"              -> "LAFEDAR"
      "BETA PM48647 x8"                -> "BETA"
    """
    brand = raw.strip()
    brand = re.sub(r"\s+(?:PM|C\.)\s*\d[\d/]*.*$", "", brand, flags=re.IGNORECASE)
    brand = re.sub(
        r"\s+(?:CAJA|VTO\.?|x\s*\d|\(|BLISTER|SEGUN|INGRESA|ALT\.?|NO\s+SE|CAJA\s+CERRADA).*$",
        "",
        brand,
        flags=re.IGNORECASE,
    ).strip()
    return brand


def _distribute_brands(rows: list[list]) -> list[list]:
    """Redistribute brand lists from merged cells to individual provider rows.

    In comparativas PDFs, pdfplumber extracts the brand info for ALL providers
    as a single multiline cell (\\n-separated) in ONE provider's Description
    column. Two patterns occur:
      A) Brand-list row has no price (standalone brand cell)
      B) Brand-list row also has a price (pdfplumber merged it with the first
         provider's row)

    This function:
      1. Finds rows where Description has \\n (with or without price)
      2. Splits brands by \\n, cleans catalog codes via _clean_brand()
      3. Distributes the N-th brand to the N-th price row in that item block
      4. Clears the multiline list from the source row

    Column layout assumed: 0=Proveedor, 1=Item, 3=Descripción, 5=PU
    """
    ITEM_COL = 1
    DESC_COL = 3
    PRICE_COL = 5

    if not rows or not any(len(r) > PRICE_COL for r in rows):
        return rows

    result = [list(r) for r in rows]

    # Group rows into item blocks: new block starts when ITEM_COL has a digit
    groups: list[list[int]] = []
    current: list[int] = []
    for i, row in enumerate(result):
        item_val = row[ITEM_COL] if len(row) > ITEM_COL else None
        if item_val is not None and str(item_val).strip().isdigit():
            if current:
                groups.append(current)
            current = [i]
        else:
            current.append(i)
    if current:
        groups.append(current)

    for group in groups:
        # Find first brand-list row: Description has \n (with or without price).
        # pdfplumber sometimes merges the brand list into the first provider row,
        # which means that row can have both \n-separated brands AND a price.
        bl_idx: int | None = None
        bl_desc = ""
        for i in group:
            row = result[i]
            desc = str(row[DESC_COL]) if len(row) > DESC_COL and row[DESC_COL] is not None else ""
            if "\n" in desc:
                bl_idx = i
                bl_desc = desc
                break

        if bl_idx is None:
            continue

        # Build ordered list of valid (non-No-cotiza) brands
        valid_brands: list[str] = []
        for line in bl_desc.split("\n"):
            b = _clean_brand(line)
            if b and b.lower() not in ("no cotiza", "nc", "no cotiza."):
                valid_brands.append(b)

        # Clear the multiline Description regardless of whether brands found
        result[bl_idx][DESC_COL] = ""

        if not valid_brands:
            continue

        # Collect ALL price rows in order (including bl_idx if it has price).
        # When bl_idx has price, brand[0] goes to it; remaining brands go to
        # subsequent price rows in document order.
        price_rows = [
            i for i in group
            if len(result[i]) > PRICE_COL
            and result[i][PRICE_COL] is not None
            and str(result[i][PRICE_COL]).strip()
        ]

        # N-th brand -> N-th price row
        for n, row_i in enumerate(price_rows):
            if n < len(valid_brands):
                result[row_i][DESC_COL] = valid_brands[n]

    return result


def _rows_to_markdown(rows: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to a Markdown pipe table."""
    if not rows:
        return ""
    str_rows = [[str(c).replace('\n', ' ').strip() if c is not None else "" for c in row] for row in rows]
    str_rows = [row for row in str_rows if any(cell for cell in row)]
    if not str_rows:
        return ""
    ncols = max(len(row) for row in str_rows)
    str_rows = [row + [""] * (ncols - len(row)) for row in str_rows]
    lines = [
        "| " + " | ".join(str_rows[0]) + " |",
        "| " + " | ".join(["---"] * ncols) + " |",
    ]
    for row in str_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _extract_native_pdf(filepath: Path) -> str:
    """Extract text from a native PDF using pdfplumber.

    Accumulates all table rows across pages into a single Markdown table,
    deduplicating repeated page headers. If a page header differs from the
    canonical one, logs a WARNING and includes it as a new section (never
    discards silently). Text-only pages are appended after the table.

    Raises RuntimeError if pdfplumber is not installed.
    """
    if not PDFPLUMBER_AVAILABLE:
        raise RuntimeError("pdfplumber is not installed")

    table_rows: list[list] = []
    canonical_header = None           # tuple[str, ...] established from first table
    header_variants: set = set()
    text_parts: list[str] = []

    with pdfplumber.open(str(filepath)) as pdf:
        page_count = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    merged = _merge_fragmented_rows(table)
                    if not merged:
                        continue
                    this_header = tuple(
                        str(c).replace('\n', ' ').strip() if c is not None else ""
                        for c in merged[0]
                    )
                    if canonical_header is None:
                        canonical_header = this_header
                        header_variants.add(this_header)
                        table_rows.extend(merged)
                    elif this_header == canonical_header:
                        table_rows.extend(merged[1:])   # skip duplicate header
                    else:
                        if this_header not in header_variants:
                            logger.warning(
                                "Header variante en pág %d: %s (esperado: %s)",
                                page_num, this_header, canonical_header,
                            )
                            header_variants.add(this_header)
                        table_rows.extend(merged)       # include variant header
            else:
                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(text.strip())

    parts: list[str] = []
    if table_rows:
        table_rows = _distribute_brands(table_rows)
        md = _rows_to_markdown(table_rows)
        if md:
            parts.append(md)
    parts.extend(text_parts)

    result = "\n\n".join(parts)
    variant_info = f", {len(header_variants)} variantes de header" if len(header_variants) > 1 else ""
    logger.info(
        "pipeline=native_pdf file=%s pages=%d chars=%d%s",
        filepath.name, page_count, len(result), variant_info,
    )
    return result


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
    """Parse a PDF file to Markdown using a hybrid pipeline.

    Pipeline decision (in order):
    1. docling unavailable      → Vision (Gemini file upload)
    2. is_scanned_pdf() = False → pdfplumber native extraction
       └ empty / error          → Docling lightweight (15-page chunks)
    3. is_scanned_pdf() = True  → Docling lightweight (15-page chunks)
    4. Docling chunk fails      → Vision per chunk (last resort)

    Docling lightweight mode disables page image generation to reduce RAM.
    gc.collect() runs after each Docling chunk.
    """
    if not DOCLING_AVAILABLE:
        logger.warning("docling not available, routing PDF to Gemini Vision: %s", filepath.name)
        return _parse_image(filepath)

    scanned = is_scanned_pdf(filepath)

    if not scanned:
        if PDFPLUMBER_AVAILABLE:
            try:
                result = _extract_native_pdf(filepath)
                if result.strip():
                    return result
                logger.warning(
                    "pdfplumber returned empty result for %s, falling back to Docling",
                    filepath.name,
                )
            except Exception as exc:
                logger.warning(
                    "pdfplumber failed for %s (%s), falling back to Docling",
                    filepath.name,
                    exc,
                )
        pipeline_label = "docling_native_fallback"
    else:
        pipeline_label = "docling_scanned"

    temp_files: list[Path] = []
    try:
        chunks = _split_pdf_by_pages(filepath, pages_per_chunk=15)
        files_to_process = chunks if chunks else [filepath]
        temp_files = chunks

        all_markdown: list[str] = []
        for idx, chunk_path in enumerate(files_to_process, start=1):
            try:
                chunk_result = _docling_convert(chunk_path, lightweight=True)
                chunk_text = chunk_result.document.export_to_markdown()
                all_markdown.append(chunk_text)
                logger.info(
                    "Parsed PDF chunk %d/%d via docling (%d chars)",
                    idx,
                    len(files_to_process),
                    len(chunk_text),
                )
            except Exception as chunk_exc:
                logger.warning("Docling chunk %d failed, using Vision: %s", idx, chunk_exc)
                chunk_text = _parse_image(chunk_path)
                all_markdown.append(chunk_text)
            gc.collect()

        text = "\n\n".join(all_markdown)
        logger.info(
            "pipeline=%s file=%s chunks=%d chars=%d",
            pipeline_label,
            filepath.name,
            len(files_to_process),
            len(text),
        )
        return text

    except Exception as exc:
        logger.warning("Docling failed for %s, falling back to Vision: %s", filepath.name, exc)
        logger.info("pipeline=vision_fallback file=%s", filepath.name)
        return _parse_image(filepath)

    finally:
        gc.collect()
        for temp_file in temp_files:
            try:
                temp_file.unlink()
                logger.debug("Cleaned up temporary chunk: %s", temp_file.name)
            except Exception as cleanup_exc:
                logger.warning("Failed to clean up chunk %s: %s", temp_file.name, cleanup_exc)


def _parse_html(filepath: Path) -> str:
    """Parse an HTML file to clean text using BeautifulSoup4.

    Skips Docling entirely — HTML price lists in this project are well-structured
    enough for BS4, which avoids the memory overhead of the Docling pipeline.

    Args:
        filepath: Path to the .html or .htm file.

    Returns:
        Clean text string (no HTML tags).
    """
    soup = BeautifulSoup(filepath.read_bytes(), "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    clean_text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    logger.info("pipeline=bs4_html file=%s chars=%d", filepath.name, len(clean_text))
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
            response = generate_with_fallback(CLIENT, [_VISION_PROMPT, uploaded_file])
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
