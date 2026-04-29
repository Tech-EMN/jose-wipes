"""Valida extração de texto e warnings de PDF no web studio."""

import sys
import types
import shutil
from pathlib import Path
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp.pdf_utils import extract_pdf_text


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdfReader:
    def __init__(self, _path):
        self.pages = [FakePage("Página 1"), FakePage("Página 2")]


class EmptyPdfReader:
    def __init__(self, _path):
        self.pages = [FakePage(""), FakePage("   ")]


def main():
    print("=" * 50)
    print("TESTE: Web PDF Utils")
    print("=" * 50)

    temp_dir = Path(__file__).parent.parent / "output" / "test_web_pdf_utils"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        pdf_path = temp_dir / "roteiro.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        fake_module = types.SimpleNamespace(PdfReader=FakePdfReader)
        with patch.dict(sys.modules, {"pypdf": fake_module}):
            text, warnings = extract_pdf_text(pdf_path, char_limit=100)
            if "Página 1" not in text or warnings:
                print(f"  ✗ Extração esperada falhou: text={text!r}, warnings={warnings}")
                return 1
            print("  ✓ Texto extraído com sucesso")

        empty_module = types.SimpleNamespace(PdfReader=EmptyPdfReader)
        with patch.dict(sys.modules, {"pypdf": empty_module}):
            text, warnings = extract_pdf_text(pdf_path, char_limit=100)
            if text or not warnings:
                print(f"  ✗ PDF vazio deveria gerar warning: text={text!r}, warnings={warnings}")
                return 1
            print("  ✓ PDF vazio gera warning sem falhar")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("-" * 50)
    print("  ✓ TESTE WEB PDF UTILS: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
