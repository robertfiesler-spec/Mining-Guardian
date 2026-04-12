"""Extract text from the two PDFs Bobby uploaded.

log 1.pdf — 18 MB tech support file from an Auradine miner
Teraflux_API_Reference.pdf — official Auradine API docs
"""
import sys
import pdfplumber
from pathlib import Path

def extract(path: str, max_pages: int = None) -> str:
    chunks = []
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        print(f"=== {path}: {total} pages ===", file=sys.stderr)
        pages_to_read = total if max_pages is None else min(total, max_pages)
        for i, page in enumerate(pdf.pages[:pages_to_read]):
            txt = page.extract_text() or ""
            chunks.append(f"\n--- PAGE {i+1}/{total} ---\n{txt}")
            if (i + 1) % 10 == 0:
                print(f"  extracted {i+1}/{pages_to_read}", file=sys.stderr)
    return "\n".join(chunks)

if __name__ == "__main__":
    target = sys.argv[1]
    max_p = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(extract(target, max_p))
