#!/usr/bin/env python
"""
preprocess_pdf_compress.py
==========================
Shrink a NUST report PDF below the Anthropic Files API ~32 MB base64-encoded
request limit. Raw 26-MB PDFs base64-encode to ~35 MB and trip the 413
request_too_large error; ~38-MB PDFs (1975 era) are even further over.

Strategy: re-emit each page as a JPEG-compressed image at a chosen DPI, then
wrap the JPEGs back into a new PDF. This is lossy but the original PDFs are
already scanned bitmap images, so we lose nothing structural — only some
pixel-level fidelity that Claude doesn't need for table reading.

Falls back to ``pikepdf.save(linearize=True, compress_streams=True,
object_stream_mode=generate)`` if Pillow is not available; that helps a bit
but rarely enough on scanned PDFs.

Usage:
    python fixes/preprocess_pdf_compress.py \\
        --in  input_files/input_1990/1990.pdf \\
        --out input_files/input_1990/1990_compressed.pdf \\
        --target_mb 22

    # Specify DPI directly (skip the auto-tune loop):
    python fixes/preprocess_pdf_compress.py --in 1975.pdf --out 1975_c.pdf --dpi 150
"""

import argparse
import io
import math
import sys
from pathlib import Path


def _compress_via_pikepdf(in_path: Path, out_path: Path) -> int:
    import pikepdf
    print(f"  Trying pikepdf structural compression...", flush=True)
    with pikepdf.open(str(in_path)) as pdf:
        pdf.save(
            str(out_path),
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=True,
        )
    return out_path.stat().st_size


def _compress_via_jpeg_pages(in_path: Path, out_path: Path, dpi: int,
                              jpeg_quality: int = 75) -> int:
    """Render every page as a JPEG at given DPI, then assemble into a new PDF.

    Uses PyMuPDF (fitz) for rendering — much faster than pdf2image and no
    Poppler dependency on Windows.
    """
    import fitz  # PyMuPDF
    print(f"  Rendering pages at dpi={dpi}, jpeg_quality={jpeg_quality}...",
          flush=True)

    src = fitz.open(str(in_path))
    out = fitz.open()
    zoom = dpi / 72.0
    mat  = fitz.Matrix(zoom, zoom)

    for page_no, page in enumerate(src, start=1):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        # Encode as JPEG in-memory
        jpeg_bytes = pix.tobytes(output="jpeg", jpg_quality=jpeg_quality)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        new_page = out.new_page(width=pix.width, height=pix.height)
        new_page.insert_image(rect, stream=jpeg_bytes)

    out.save(str(out_path), deflate=True, garbage=4, clean=True)
    out.close()
    src.close()
    return out_path.stat().st_size


def base64_size_estimate(file_size_bytes: int) -> int:
    """Base64 expands by 4/3 (plus a constant for line wraps)."""
    return math.ceil(file_size_bytes * 4 / 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",  dest="in_path",  required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--target_mb", type=float, default=22.0,
                    help="Target file size in MB after compression "
                         "(default 22 MB ≈ 29 MB base64, under the 32 MB API cap)")
    ap.add_argument("--dpi", type=int, default=None,
                    help="Skip auto-tune; render at this DPI")
    ap.add_argument("--jpeg_quality", type=int, default=75)
    args = ap.parse_args()

    in_path  = Path(args.in_path)
    out_path = Path(args.out_path)
    if not in_path.exists():
        print(f"Error: {in_path} not found", file=sys.stderr)
        sys.exit(1)

    raw_bytes = in_path.stat().st_size
    print(f"Input:  {in_path}  ({raw_bytes/1024/1024:.1f} MB raw, "
          f"{base64_size_estimate(raw_bytes)/1024/1024:.1f} MB base64-est)",
          flush=True)
    target_bytes = int(args.target_mb * 1024 * 1024)

    if raw_bytes <= target_bytes:
        print("Input already under target — copying as-is.", flush=True)
        out_path.write_bytes(in_path.read_bytes())
        print(f"Output: {out_path}  ({out_path.stat().st_size/1024/1024:.1f} MB)")
        return

    # Step 1: try pikepdf structural compression
    pikepdf_size = None
    try:
        pikepdf_size = _compress_via_pikepdf(in_path, out_path)
        print(f"  pikepdf result: {pikepdf_size/1024/1024:.1f} MB", flush=True)
        if pikepdf_size <= target_bytes:
            print(f"Output: {out_path}  ({pikepdf_size/1024/1024:.1f} MB) [pikepdf]")
            return
    except ImportError:
        print("  pikepdf not installed — skipping structural step", flush=True)
    except Exception as e:
        print(f"  pikepdf failed: {e}", flush=True)

    # Step 2: JPEG re-encode. Try given DPI, or auto-tune from 200 → 100.
    dpi_candidates = [args.dpi] if args.dpi else [200, 175, 150, 125, 110, 100]
    best_size, best_dpi = None, None
    for dpi in dpi_candidates:
        try:
            sz = _compress_via_jpeg_pages(in_path, out_path, dpi,
                                          args.jpeg_quality)
        except ImportError as e:
            print(f"  PyMuPDF (fitz) not installed: {e}", file=sys.stderr)
            sys.exit(2)
        print(f"  dpi={dpi}: {sz/1024/1024:.1f} MB", flush=True)
        if sz <= target_bytes:
            best_size, best_dpi = sz, dpi
            break
        # Keep the smallest result regardless
        if best_size is None or sz < best_size:
            best_size, best_dpi = sz, dpi

    final = out_path.stat().st_size
    print(f"\nOutput: {out_path}  ({final/1024/1024:.1f} MB raw, "
          f"{base64_size_estimate(final)/1024/1024:.1f} MB base64-est) "
          f"[dpi={best_dpi}]")

    if final > target_bytes:
        print(f"WARNING: did not reach target {args.target_mb} MB — "
              f"consider lowering --jpeg_quality or --dpi.", file=sys.stderr)


if __name__ == "__main__":
    main()
