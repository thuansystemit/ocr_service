"""Standalone PDF text-extraction smoke check (Sprint 1).

This is **not** the production parser (that is C-11 / ``app/pipeline/parsers/``,
delivered in Sprint 3). It exists only to prove that the parsing dependencies
installed in Sprint 1 (``pdfplumber`` + ``pytesseract`` / ``tesseract-ocr``) can
pull text out of a real PDF inside the container. It takes no DB and no network.

Run it inside the already-built test image (see docs/sprint1/TESTING.md):

    docker run --rm -v "$PWD/samples:/samples" ocr-service-test:latest \
        python docs/sprint1/parse_pdf_smoke.py /samples/your-document.pdf

Exit codes: 0 = text extracted, 3 = opened but ~empty (likely a scanned PDF that
needs OCR), 2 = usage/IO error.
"""

from __future__ import annotations

import sys

import pdfplumber


def extract_text(path: str) -> str:
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(f"--- page {i} ---\n{text}")
    return "\n\n".join(pages)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: parse_pdf_smoke.py <file.pdf>", file=sys.stderr)
        return 2
    try:
        result = extract_text(argv[1])
    except Exception as exc:  # noqa: BLE001 - smoke script, surface any failure
        print(f"[error] could not parse {argv[1]}: {exc}", file=sys.stderr)
        return 2

    print(result)
    chars = len(result.replace("\n", "").strip())
    print(f"\n[info] extracted ~{chars} non-whitespace chars", file=sys.stderr)
    if chars < 10:
        print(
            "[warn] little/no embedded text — this looks like a scanned PDF. "
            "The Sprint 3 parser falls back to OCR (pytesseract) for these.",
            file=sys.stderr,
        )
        return 3
    print("[ok] PDF parsing dependencies are working.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
