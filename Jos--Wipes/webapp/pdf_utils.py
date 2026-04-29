"""PDF helpers for extracting script context from uploaded files."""

from __future__ import annotations

from pathlib import Path


MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 12_000


def extract_pdf_text(pdf_path: Path, char_limit: int = MAX_PDF_TEXT_CHARS) -> tuple[str, list[str]]:
    """Extract text from a PDF while returning non-fatal warnings."""

    warnings: list[str] = []

    try:
        from pypdf import PdfReader
    except ImportError:
        warnings.append("Leitura de PDF indisponível: instale a dependência `pypdf`.")
        return "", warnings

    try:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(text)
    except Exception as exc:
        warnings.append(f"Não foi possível extrair texto do PDF: {exc}")
        return "", warnings

    text = "\n\n".join(parts).strip()
    if not text:
        warnings.append("Nenhum texto legível foi encontrado no PDF enviado.")
        return "", warnings

    if len(text) > char_limit:
        text = text[:char_limit].rstrip()
        warnings.append("O texto do PDF foi truncado para manter o planejamento seguro e previsível.")

    return text, warnings
