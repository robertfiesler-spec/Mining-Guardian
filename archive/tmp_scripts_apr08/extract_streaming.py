"""Stream-extract a large PDF page-by-page directly to disk.

Avoids buffering the entire extraction in memory. Writes each page as soon as
it's parsed, so partial results are usable even if the process is killed.
"""
import sys
import pdfplumber

src = sys.argv[1]
dst = sys.argv[2]

with pdfplumber.open(src) as pdf:
    total = len(pdf.pages)
    print(f"=== {src}: {total} pages ===", file=sys.stderr)
    with open(dst, 'w') as out:
        for i, page in enumerate(pdf.pages):
            try:
                txt = page.extract_text() or ""
            except Exception as e:
                txt = f"<<extract failed: {e}>>"
            out.write(f"\n--- PAGE {i+1}/{total} ---\n{txt}\n")
            out.flush()
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{total} pages written", file=sys.stderr)
print("DONE", file=sys.stderr)
