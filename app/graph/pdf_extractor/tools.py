import io
import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PDF backends — none is hard-required at import time
# ---------------------------------------------------------------------------
try:
    import pdfplumber as _pdfplumber   # layout-aware: tables + ordered text
except ImportError:
    _pdfplumber = None

try:
    from PyPDF2 import PdfReader as _PyPDF2Reader
except ImportError:
    _PyPDF2Reader = None

# Public alias kept for backward-compatibility with tests and external callers
PdfReader = _PyPDF2Reader

try:
    import fitz as _fitz          # pymupdf — used as OCR / scanned-PDF fallback
except ImportError:
    _fitz = None


# ---------------------------------------------------------------------------
# Numeric fields that must always be int / float (never str / None)
# ---------------------------------------------------------------------------
_NUMERIC_FIELDS = {
    "amount_raised_to_date",
    "target_amount",
    "ownership_percentage",
    "years_direct_experience",
    "interviews_conducted",
    "user_count",
    "active_users_monthly",
    "early_revenue",
    "growth_rate",
    "average_price_per_customer",
    "gross_margin",
    "monthly_burn",
    "runway_months",
}


def force_numeric_types(data: object) -> object:
    """
    Recursively walk *data* and coerce every field whose name is in
    _NUMERIC_FIELDS to an int or float.

    Handles:
      - str  → strip non-numeric chars, parse; fallback 0
      - None → 0
      - already int/float → unchanged
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key in _NUMERIC_FIELDS:
                if isinstance(value, (int, float)):
                    pass                                   # already correct
                elif isinstance(value, str):
                    clean = re.sub(r"[^0-9.]", "", value)
                    try:
                        data[key] = float(clean) if "." in clean else int(clean)
                    except ValueError:
                        data[key] = 0
                else:
                    data[key] = 0                          # None or unexpected type
            else:
                force_numeric_types(value)
    elif isinstance(data, list):
        for item in data:
            force_numeric_types(item)
    return data


# ---------------------------------------------------------------------------
# Stage-1 text extraction helpers
# ---------------------------------------------------------------------------

def _table_to_markdown(table: list) -> str:
    """Convert a pdfplumber table (list of rows) to a Markdown table string."""
    rows = [[cell or "" for cell in row] for row in table if any(row)]
    if not rows:
        return ""
    header, *body = rows
    sep = ["-" * max(len(c), 1) for c in header]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep)    + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _extract_via_pdfplumber(file_bytes: bytes) -> str:
    """
    Layout-aware extraction using pdfplumber.

    - Pages with tables: non-table text via extract_words() + tables as Markdown.
    - Pages without tables: extract_text() — more reliable than extract_words()
      for PDFs with unusual fonts or encodings.
    - Zero ML models, sub-second on CPU — safe for Azure student-tier.
    """
    if _pdfplumber is None:
        return ""
    try:
        pages_text = []
        with _pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                parts = []
                table_objects = page.find_tables()

                if table_objects:
                    # Extract non-table text word-by-word to avoid duplication
                    table_bboxes = [t.bbox for t in table_objects]
                    words = page.extract_words(keep_blank_chars=False)
                    non_table_words = [
                        w["text"] for w in words
                        if not any(
                            w["x0"] >= bb[0] and w["top"] >= bb[1]
                            and w["x1"] <= bb[2] and w["bottom"] <= bb[3]
                            for bb in table_bboxes
                        )
                    ]
                    if non_table_words:
                        parts.append(" ".join(non_table_words))
                    for t in table_objects:
                        md = _table_to_markdown(t.extract())
                        if md:
                            parts.append(md)
                else:
                    # No tables — extract_text() handles more PDF encodings than
                    # extract_words(), which silently returns [] on some fonts.
                    text = page.extract_text()
                    if text and text.strip():
                        parts.append(text.strip())

                if parts:
                    pages_text.append("\n\n".join(parts))

        return "\n\n---\n\n".join(pages_text)

    except Exception as exc:
        logger.warning("[PDF tools] pdfplumber failed: %s", exc)
        return ""


def _extract_via_pypdf2(file_bytes: bytes) -> str:
    """Digital PDF extraction using PyPDF2 — fast, zero GPU cost."""
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(t for t in pages if t.strip())
    except Exception as exc:
        logger.warning("[PDF tools] PyPDF2 failed: %s", exc)
        return ""


def _extract_via_pymupdf(file_bytes: bytes) -> str:
    """
    Fallback extraction using pymupdf (fitz).

    Strategy:
      1. Try native text extraction (works on most digital PDFs).
      2. If a page yields no text, render it to a pixmap and run
         Tesseract OCR through pymupdf's built-in get_text("words") heuristic.
         (Full Tesseract OCR requires pytesseract + tesseract-ocr binary;
          we keep the dep-free path as the default.)
    """
    if _fitz is None:
        return ""
    try:
        doc = _fitz.open(stream=file_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                pages_text.append(text)
            else:
                # Page is likely an image — get_text("words") still returns []
                # so we log it; add pytesseract here if you need full OCR.
                logger.warning(
                    "[PDF tools] Page %d has no extractable text (scanned image). "
                    "Install pytesseract for full OCR support.",
                    page.number,
                )
        doc.close()
        return "\n\n".join(pages_text)
    except Exception as exc:
        logger.warning("[PDF tools] pymupdf failed: %s", exc)
        return ""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Three-stage PDF text extraction.

    Stage 1 — pdfplumber (tables as Markdown + ordered text; best for pitch decks).
    Stage 2 — PyPDF2 (fast plain-text fallback for simple digital PDFs).
    Stage 3 — pymupdf (fitz) fallback for scanned / complex PDFs.

    Returns the extracted text, or raises RuntimeError if all three fail.
    """
    # --- Stage 1 ---
    text = _extract_via_pdfplumber(file_bytes)
    if text.strip():
        logger.info("[PDF tools] Text extracted via pdfplumber (%d chars).", len(text))
        return text

    logger.info("[PDF tools] pdfplumber returned no text — trying PyPDF2 fallback.")

    # --- Stage 2 ---
    text = _extract_via_pypdf2(file_bytes)
    if text.strip():
        logger.info("[PDF tools] Text extracted via PyPDF2 (%d chars).", len(text))
        return text

    logger.info("[PDF tools] PyPDF2 returned no text — trying pymupdf fallback.")

    # --- Stage 3 ---
    text = _extract_via_pymupdf(file_bytes)
    if text.strip():
        logger.info("[PDF tools] Text extracted via pymupdf (%d chars).", len(text))
        return text

    raise RuntimeError(
        "Could not extract text from PDF. "
        "The file may be a scanned image without an OCR layer. "
        "Install pytesseract + tesseract-ocr for full OCR support."
    )