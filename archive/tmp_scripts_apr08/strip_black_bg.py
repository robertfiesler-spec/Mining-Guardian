"""Strip the black background from the Mining Guardian wordmark PNG.

The original has hasAlpha:no with a fully painted black background. We
load it, add an alpha channel, and replace any pixel that's pure black
or very close to it with transparent. The wordmark text and effects
(silver, blue, orange sparkles) are well above the threshold so they
survive intact.

Also processes the icon and primary logo for consistency.
"""
import sys
from PIL import Image
from pathlib import Path

def strip_black(src_path: str, dst_path: str, threshold: int = 25) -> None:
    """Replace near-black pixels with transparent.

    threshold: max RGB sum for a pixel to be considered "black" (0-765).
               25 catches pure #000-#080808 range. Higher values would
               start eating into dark blue/purple parts of the logo.
    """
    img = Image.open(src_path).convert("RGBA")
    pixels = img.load()
    w, h = img.size
    changed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r + g + b <= threshold:
                pixels[x, y] = (0, 0, 0, 0)  # fully transparent
                changed += 1
    img.save(dst_path, "PNG")
    print(f"  {src_path} -> {dst_path}")
    print(f"    {w}x{h}, {changed:,} pixels made transparent ({changed*100/(w*h):.1f}%)")

if __name__ == "__main__":
    base = "/root/Mining-Gaurdian/branding"
    out  = "/root/Mining-Gaurdian/branding"
    print("Stripping black backgrounds from Mining Guardian logos...")
    for name in ["mining_guardian_horizontal_wordmark",
                 "mining_guardian_mg_icon",
                 "mining_guardian_primary",
                 "mining_guardian_stacked_wordmark"]:
        src = f"{base}/{name}.png"
        dst = f"{out}/{name}_transparent.png"
        if Path(src).exists():
            strip_black(src, dst)
        else:
            print(f"  SKIP {src} (not found)")
    print("Done.")
