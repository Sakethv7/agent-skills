"""
doc-tools MCP server

Exposes PDF and OCR operations as MCP tools so any agent can call them
mid-task without running shell commands directly.

Dependencies: poppler-utils, tesseract-ocr (system), mcp (pip)
"""

import base64
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "doc-tools",
    instructions=(
        "Tools for extracting text and images from PDFs. "
        "Always call detect_text_layer first — if it returns has_text_layer=true, "
        "use extract_text instead of ocr_pages. OCR is slower and less accurate "
        "than a native text layer."
    ),
)


def _require(cmd: str) -> None:
    if not shutil.which(cmd):
        raise RuntimeError(
            f"'{cmd}' not found. "
            "Install: brew install poppler tesseract (macOS) "
            "or apt-get install poppler-utils tesseract-ocr (Linux)"
        )


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def pdf_info(path: str) -> dict:
    """
    Return metadata about a PDF: page count, title, author, creator,
    file size, and whether it is encrypted.

    Args:
        path: Absolute path to the PDF file.
    """
    _require("pdfinfo")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No file at {path}")

    result = _run(["pdfinfo", path], check=False)
    info: dict = {"path": path, "size_bytes": p.stat().st_size}

    for line in result.stdout.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            info[key.strip().lower().replace(" ", "_")] = val.strip()

    # Normalise page count to int
    if "pages" in info:
        try:
            info["pages"] = int(info["pages"])
        except ValueError:
            pass

    return info


@mcp.tool()
def detect_text_layer(path: str, sample_pages: int = 3) -> dict:
    """
    Check whether a PDF has a usable embedded text layer.
    Returns has_text_layer (bool), char_count, and a short sample of the text.

    Use this before deciding whether to call extract_text or ocr_pages.

    Args:
        path: Absolute path to the PDF file.
        sample_pages: Number of pages to sample (default 3). Faster than full doc.
    """
    _require("pdftotext")
    if not Path(path).exists():
        raise FileNotFoundError(f"No file at {path}")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp = f.name

    # Extract only the first N pages for speed
    _run(["pdftotext", "-l", str(sample_pages), path, tmp], check=False)
    text = Path(tmp).read_text(errors="replace")
    Path(tmp).unlink(missing_ok=True)

    char_count = len(text.strip())
    # Heuristic: real text layers have > 100 chars per page sampled
    has_layer = char_count > (100 * sample_pages)

    return {
        "has_text_layer": has_layer,
        "char_count": char_count,
        "sample": text[:500].strip(),
        "recommendation": "use extract_text" if has_layer else "use ocr_pages",
    }


@mcp.tool()
def extract_text(
    path: str,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    layout: bool = False,
) -> dict:
    """
    Extract text from a PDF using its native text layer (fast, accurate).
    Only use this when detect_text_layer returns has_text_layer=true.

    Args:
        path: Absolute path to the PDF file.
        start_page: First page to extract (1-indexed). None = beginning.
        end_page: Last page to extract (1-indexed). None = end.
        layout: If true, preserve approximate layout with whitespace (slower).
    """
    _require("pdftotext")
    if not Path(path).exists():
        raise FileNotFoundError(f"No file at {path}")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp = f.name

    args = ["pdftotext"]
    if layout:
        args.append("-layout")
    if start_page is not None:
        args += ["-f", str(start_page)]
    if end_page is not None:
        args += ["-l", str(end_page)]
    args += [path, tmp]

    _run(args)
    text = Path(tmp).read_text(errors="replace")
    Path(tmp).unlink(missing_ok=True)

    return {
        "text": text,
        "char_count": len(text),
        "start_page": start_page,
        "end_page": end_page,
    }


@mcp.tool()
def ocr_pages(
    path: str,
    start_page: int,
    end_page: int,
    dpi: int = 200,
    lang: str = "eng",
) -> dict:
    """
    OCR a page range from a scanned PDF using pdftoppm + tesseract.
    Slower than extract_text — only use when detect_text_layer returns
    has_text_layer=false.

    Args:
        path: Absolute path to the PDF file.
        start_page: First page to OCR (1-indexed).
        end_page: Last page to OCR (1-indexed, inclusive).
        dpi: Rasterization resolution. 200 is the sweet spot for accuracy vs speed.
             Use 150 for faster runs on clean scans, 300 for small/dense text.
        lang: Tesseract language code (default "eng"). Use "fra", "deu", etc.
              Run `tesseract --list-langs` to see installed languages.
    """
    _require("pdftoppm")
    _require("tesseract")
    if not Path(path).exists():
        raise FileNotFoundError(f"No file at {path}")
    if end_page < start_page:
        raise ValueError(f"end_page ({end_page}) must be >= start_page ({start_page})")

    with tempfile.TemporaryDirectory() as tmp_dir:
        prefix = str(Path(tmp_dir) / "page")
        _run([
            "pdftoppm", "-jpeg",
            "-r", str(dpi),
            "-f", str(start_page),
            "-l", str(end_page),
            path, prefix,
        ])

        pages = sorted(
            Path(tmp_dir).glob("page-*.jpg"),
            key=lambda p: int(re.search(r"-(\d+)\.jpg$", p.name).group(1)),
        )

        if not pages:
            raise RuntimeError(
                f"pdftoppm produced no output for pages {start_page}-{end_page}. "
                "The PDF may be encrypted or the page range may be out of bounds."
            )

        texts: list[str] = []
        for img in pages:
            result = _run(
                ["tesseract", str(img), "stdout", "-l", lang],
                check=False,
            )
            texts.append(result.stdout)

        full_text = "\n".join(texts)

    return {
        "text": full_text,
        "char_count": len(full_text),
        "pages_processed": len(texts),
        "start_page": start_page,
        "end_page": end_page,
        "dpi": dpi,
        "lang": lang,
    }


@mcp.tool()
def rasterize_pages(
    path: str,
    start_page: int,
    end_page: int,
    dpi: int = 150,
) -> dict:
    """
    Convert a page range to JPEG images, returned as base64-encoded strings.
    Use this when you need to pass page images to a vision model or embed them
    in an HTML viewer.

    Args:
        path: Absolute path to the PDF file.
        start_page: First page (1-indexed).
        end_page: Last page (1-indexed, inclusive). Keep ranges short (<20 pages)
                  to avoid large payloads.
        dpi: Resolution. 150 is good for viewing; use 72 for thumbnails.
    """
    _require("pdftoppm")
    if not Path(path).exists():
        raise FileNotFoundError(f"No file at {path}")
    if end_page - start_page > 30:
        raise ValueError(
            "Rasterizing more than 30 pages at once will produce a very large payload. "
            "Split into smaller ranges."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        prefix = str(Path(tmp_dir) / "page")
        _run([
            "pdftoppm", "-jpeg",
            "-r", str(dpi),
            "-f", str(start_page),
            "-l", str(end_page),
            path, prefix,
        ])

        pages = sorted(
            Path(tmp_dir).glob("page-*.jpg"),
            key=lambda p: int(re.search(r"-(\d+)\.jpg$", p.name).group(1)),
        )

        images = []
        for i, img_path in enumerate(pages):
            b64 = base64.b64encode(img_path.read_bytes()).decode()
            images.append({
                "page": start_page + i,
                "data_uri": f"data:image/jpeg;base64,{b64}",
                "size_bytes": img_path.stat().st_size,
            })

    return {
        "images": images,
        "count": len(images),
        "dpi": dpi,
    }


@mcp.tool()
def extract_toc(path: str, max_toc_page: int = 12) -> dict:
    """
    Attempt to extract the table of contents from a PDF. Tries the native text
    layer first; falls back to OCR on the first N pages if needed.

    Returns a list of {title, page} entries if found, or raw_text if the TOC
    couldn't be parsed into structured entries.

    Args:
        path: Absolute path to the PDF file.
        max_toc_page: How many pages to scan for the TOC (default 12).
    """
    _require("pdftotext")

    # Try native text layer
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        tmp = f.name
    _run(["pdftotext", "-l", str(max_toc_page), path, tmp], check=False)
    raw = Path(tmp).read_text(errors="replace")
    Path(tmp).unlink(missing_ok=True)

    if len(raw.strip()) < 100:
        # Fall back to OCR
        _require("pdftoppm")
        _require("tesseract")
        with tempfile.TemporaryDirectory() as tmp_dir:
            prefix = str(Path(tmp_dir) / "page")
            _run(["pdftoppm", "-jpeg", "-r", "150", "-f", "1",
                  "-l", str(max_toc_page), path, prefix])
            pages = sorted(Path(tmp_dir).glob("page-*.jpg"))
            parts = []
            for img in pages:
                r = _run(["tesseract", str(img), "stdout"], check=False)
                parts.append(r.stdout)
            raw = "\n".join(parts)

    # Heuristic parse: lines that end with a number are likely TOC entries
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^(.+?)\s+\.{2,}\s*(\d+)\s*$|^(.+?)\s{3,}(\d+)\s*$", line)
        if m:
            title = (m.group(1) or m.group(3)).strip()
            page = int(m.group(2) or m.group(4))
            if title and 1 <= page <= 9999:
                entries.append({"title": title, "page": page})

    return {
        "entries": entries,
        "parsed": len(entries) > 0,
        "raw_text": raw if not entries else None,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
