---
name: pdf-to-book
description: >
  Convert any scanned PDF — textbook, paper, manual — into a polished, self-contained
  HTML file with searchable OCR text, original scan images for figures, and KaTeX-rendered
  formulas. Provider-agnostic: auto-detects OpenAI or Anthropic from env vars. Use this
  skill when the user says "/pdf-to-book", "convert this PDF to HTML", "make this book
  readable", "OCR this textbook", or wants a browser-readable version of a scanned document
  with working math rendering.
---

# /pdf-to-book

Convert any scanned PDF into a readable HTML file with searchable OCR text, original scan images for figures, and KaTeX-rendered formulas.

**Provider-agnostic:** works with OpenAI (GPT-4.1) or Anthropic (Claude Haiku/Sonnet). Auto-detects from env vars, or the user picks.

## Usage

```
/pdf-to-book [path/to/book.pdf]
```

---

## Steps

### 1. Get inputs

- PDF path: from `$ARGUMENTS` or ask the user
- Workspace dir: default to a folder named after the PDF stem in the same directory as the PDF (e.g. `book/` next to `book.pdf`)
- Provider: check `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in env — if both are set ask the user to pick, if one is set use it, if neither is set tell the user to export one

### 2. Install dependencies

```bash
pip3 install pypdf openai anthropic --quiet --break-system-packages 2>/dev/null || pip3 install pypdf openai anthropic --quiet
```

### 3. Write pipeline scripts

Write the three scripts below into `<workspace>/scripts/` if they don't already exist. Never overwrite existing scripts.

---

#### `<workspace>/scripts/extract.py`

```python
#!/usr/bin/env python3
"""Extract one page image per PDF page and write a manifest. Resumable."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", help="Path to the scanned PDF")
    parser.add_argument("workspace", help="Workspace directory")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    pages_dir = workspace / "pages"
    manifest_path = workspace / "page_manifest.csv"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Load existing manifest to resume without re-extracting
    existing: dict[int, dict] = {}
    if manifest_path.exists():
        with manifest_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[int(row["page"])] = row

    reader = PdfReader(args.pdf_path)
    rows: list[dict] = []

    for page_index, page in enumerate(reader.pages, start=1):
        if page_index in existing:
            rows.append(existing[page_index])
            continue

        images = list(page.images)
        if not images:
            rows.append({
                "page": page_index, "status": "no_image", "image_path": "",
                "width_px": "", "height_px": "",
                "pdf_width": float(page.mediabox.width),
                "pdf_height": float(page.mediabox.height),
            })
            continue

        image = images[0]
        suffix = Path(image.name).suffix.lower() or ".jpg"
        out = pages_dir / f"page_{page_index:03d}{suffix}"
        if not out.exists():
            out.write_bytes(image.data)

        w, h = image.image.size
        rows.append({
            "page": page_index, "status": "extracted",
            "image_path": str(out), "width_px": w, "height_px": h,
            "pdf_width": float(page.mediabox.width),
            "pdf_height": float(page.mediabox.height),
        })

    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["page", "status", "image_path", "width_px", "height_px", "pdf_width", "pdf_height"]
        )
        writer.writeheader()
        writer.writerows(rows)

    extracted = sum(1 for r in rows if r["status"] == "extracted")
    skipped = sum(1 for r in rows if r["status"] == "no_image")
    print(f"Pages: {len(rows)} total, {extracted} extracted, {skipped} skipped (no image)")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
```

---

#### `<workspace>/scripts/ocr.py`

```python
#!/usr/bin/env python3
"""OCR scanned book pages with OpenAI or Anthropic vision models. Resumable."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "page": {"type": "integer"},
        "model_used": {"type": "string"},
        "quality": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "scan_readability": {"type": "string"},
                "ocr_confidence": {"type": "string"},
                "needs_human_review": {"type": "boolean"},
                "notes": {"type": "string"},
            },
            "required": ["scan_readability", "ocr_confidence", "needs_human_review", "notes"],
        },
        "running_header": {"type": "string"},
        "running_footer": {"type": "string"},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "chapter_heading", "section_heading", "subsection_heading",
                            "paragraph", "bullet_list", "numbered_list",
                            "formula", "figure", "table", "caption", "footer", "unknown",
                        ],
                    },
                    "text": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                    "latex": {"type": "string"},
                    "caption": {"type": "string"},
                    "figure_id": {"type": "string"},
                    "figure_type": {"type": "string"},
                    "raw_text_inside_figure": {"type": "array", "items": {"type": "string"}},
                    "diagram_description": {"type": "string"},
                    "needs_diagram_rebuild": {"type": "boolean"},
                },
                "required": [
                    "type", "text", "items", "latex", "caption", "figure_id",
                    "figure_type", "raw_text_inside_figure", "diagram_description",
                    "needs_diagram_rebuild",
                ],
            },
        },
    },
    "required": ["page", "model_used", "quality", "running_header", "running_footer", "blocks"],
}


OPENAI_PRICE_PER_1M = {
    "gpt-4.1":  {"input": 2.00,  "output": 8.00},
    "gpt-4o":   {"input": 2.50,  "output": 10.00},
}

ANTHROPIC_PRICE_PER_1M = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
}


@dataclass(frozen=True)
class Page:
    number: int
    image_path: Path


def load_pages(workspace: Path, start: int | None, end: int | None, only: set[int] | None) -> list[Page]:
    manifest = workspace / "page_manifest.csv"
    pages: list[Page] = []
    with manifest.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != "extracted":
                continue
            n = int(row["page"])
            if start is not None and n < start:
                continue
            if end is not None and n > end:
                continue
            if only is not None and n not in only:
                continue
            pages.append(Page(number=n, image_path=Path(row["image_path"])))
    return pages


def encode_image(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return base64.b64encode(path.read_bytes()).decode("ascii"), media_type


def ocr_prompt(page_number: int) -> str:
    return f"""You are reconstructing a scanned technical book page into structured JSON.

Page number: {page_number}

Rules:
- Transcribe the visible page faithfully. Do not summarize.
- Remove scanning artifacts, page shadows, and bleed-through noise.
- Keep running header/footer separately.
- Repair obvious line-break hyphenation.
- For formulas, provide LaTeX.
- For figures, capture caption, visible labels, diagram type, and a concise semantic description.
- Set needs_diagram_rebuild=true for figures/charts/architecture diagrams.
- If a region is unreadable, include best reading and set needs_human_review=true.
"""


# ── OpenAI backend ────────────────────────────────────────────────────────────

def ocr_openai(client: Any, model: str, page: Page) -> tuple[dict[str, Any], int, int]:
    b64, media_type = encode_image(page.image_path)
    image_url = f"data:{media_type};base64,{b64}"
    response = client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": ocr_prompt(page.number)},
                {"type": "input_image", "image_url": image_url},
            ],
        }],
        text={
            "format": {
                "type": "json_schema",
                "name": "page_extraction",
                "schema": PAGE_SCHEMA,
                "strict": True,
            }
        },
    )
    raw = ""
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            raw += getattr(content, "text", "")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    return json.loads(raw), in_tok, out_tok


# ── Anthropic backend ─────────────────────────────────────────────────────────

def ocr_anthropic(client: Any, model: str, page: Page) -> tuple[dict[str, Any], int, int]:
    b64, media_type = encode_image(page.image_path)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[{
            "name": "page_data",
            "description": "Structured content extracted from one scanned book page.",
            "input_schema": PAGE_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "page_data"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": ocr_prompt(page.number)},
            ],
        }],
    )
    result: dict[str, Any] = {}
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            result = block.input
            break
    if not result:
        raise ValueError("No tool_use block in Anthropic response")
    in_tok = getattr(response.usage, "input_tokens", 0) or 0
    out_tok = getattr(response.usage, "output_tokens", 0) or 0
    return result, in_tok, out_tok


# ── Cost tracking ─────────────────────────────────────────────────────────────

def estimate_cost(provider: str, model: str, in_tok: int, out_tok: int) -> float:
    table = OPENAI_PRICE_PER_1M if provider == "openai" else ANTHROPIC_PRICE_PER_1M
    prices = table.get(model, {"input": 0, "output": 0})
    return in_tok / 1_000_000 * prices["input"] + out_tok / 1_000_000 * prices["output"]


def append_usage(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "
")


# ── Per-page worker ───────────────────────────────────────────────────────────

def process_page(
    ocr_fn: Any, model: str, price_fn: Any,
    page: Page, ocr_dir: Path, usage_log: Path, force: bool,
) -> tuple[str, float]:
    out = ocr_dir / f"page_{page.number:03d}.json"
    if out.exists() and not force:
        return f"page {page.number}: skip (exists)", 0.0

    data, in_tok, out_tok = ocr_fn(page)
    cost = price_fn(in_tok, out_tok)
    data["page"] = page.number
    data["model_used"] = model

    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)

    append_usage(usage_log, {
        "page": page.number, "model": model,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "estimated_cost_usd": round(cost, 6),
    })
    return f"page {page.number}: ocr (${cost:.4f} est)", cost


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_only(value: str | None) -> set[int] | None:
    if not value:
        return None
    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", help="Workspace directory")
    parser.add_argument("--provider", choices=["openai", "anthropic"], help="AI provider (auto-detected from env if omitted)")
    parser.add_argument("--model", help="Model name override")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--only", help="e.g. 1-10,21,25")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    # Auto-detect provider
    provider = args.provider
    if not provider:
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if has_openai and has_anthropic:
            print("Both OPENAI_API_KEY and ANTHROPIC_API_KEY are set. Pass --provider openai or --provider anthropic.", file=sys.stderr)
            return 2
        elif has_openai:
            provider = "openai"
        elif has_anthropic:
            provider = "anthropic"
        else:
            print("No API key found. Export OPENAI_API_KEY or ANTHROPIC_API_KEY.", file=sys.stderr)
            return 2

    # Select model and client
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("OPENAI_API_KEY is not set.", file=sys.stderr)
            return 2
        from openai import OpenAI
        client = OpenAI()
        model = args.model or "gpt-4.1"
        ocr_fn = lambda p: ocr_openai(client, model, p)
        price_fn = lambda i, o: estimate_cost("openai", model, i, o)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
            return 2
        from anthropic import Anthropic
        client = Anthropic()
        model = args.model or "claude-haiku-4-5-20251001"
        ocr_fn = lambda p: ocr_anthropic(client, model, p)
        price_fn = lambda i, o: estimate_cost("anthropic", model, i, o)

    workspace = Path(args.workspace)
    ocr_dir = workspace / "ocr" / "pages"
    usage_log = workspace / "ocr" / "usage_log.jsonl"
    ocr_dir.mkdir(parents=True, exist_ok=True)

    pages = load_pages(workspace, args.start, args.end, parse_only(args.only))
    if not pages:
        print("No pages selected.")
        return 0

    print(f"Provider: {provider}  Model: {model}")
    print(f"Pages selected: {len(pages)}")

    total_cost = 0.0
    budget_hit = False
    started = time.time()

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        pending = list(pages)
        futures: dict[Any, Page] = {}
        while pending and len(futures) < max(1, args.workers):
            p = pending.pop(0)
            futures[pool.submit(process_page, ocr_fn, model, price_fn, p, ocr_dir, usage_log, args.force)] = p

        while futures:
            for future in as_completed(list(futures)):
                pg = futures.pop(future)
                try:
                    msg, cost = future.result()
                    total_cost += cost
                    print(msg, flush=True)
                    if args.budget_usd is not None and total_cost >= args.budget_usd:
                        budget_hit = True
                except Exception as exc:
                    print(f"page {pg.number}: ERROR {exc}", file=sys.stderr, flush=True)

                if not budget_hit and pending:
                    nxt = pending.pop(0)
                    futures[pool.submit(process_page, ocr_fn, model, price_fn, nxt, ocr_dir, usage_log, args.force)] = nxt
                break

    if budget_hit:
        print(f"Stopped: budget ${args.budget_usd:.2f} reached")
    print(f"Estimated cost this run: ${total_cost:.4f}")
    print(f"Done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

#### `<workspace>/scripts/build.py`

```python
#!/usr/bin/env python3
"""Build a readable HTML book from page-level OCR JSON.

Figures: shows the original extracted page scan image — no AI reconstruction.
Formulas: rendered by KaTeX via CDN (requires internet on first open).
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def render_figure(block: dict[str, Any], page_num: int, pages_rel: str) -> str:
    caption = block.get("caption") or block.get("text") or ""
    # Find the actual image extension in the pages directory
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = f"{pages_rel}/page_{page_num:03d}{ext}"
        # We can't check existence at render time without the full path, so prefer .jpg
        # The extract script always writes .jpg for JPEG pages
        break
    img_src = f"{pages_rel}/page_{page_num:03d}.jpg"
    return (
        '<figure class="figure scan-figure">'
        f'<img src="{img_src}" class="page-scan" loading="lazy" alt="{esc(caption)}">'
        f"<figcaption>{esc(caption)}</figcaption>"
        "</figure>"
    )


def render_block(block: dict[str, Any], page_num: int, pages_rel: str) -> str:
    kind = block.get("type", "unknown")
    text = block.get("text", "")
    if kind == "chapter_heading":    return f'<h1 class="chapter-title">{esc(text)}</h1>'
    if kind == "section_heading":    return f"<h2>{esc(text)}</h2>"
    if kind == "subsection_heading": return f"<h3>{esc(text)}</h3>"
    if kind == "paragraph":          return f"<p>{esc(text)}</p>"
    if kind == "bullet_list":        return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in block.get("items", [])) + "</ul>"
    if kind == "numbered_list":      return "<ol>" + "".join(f"<li>{esc(i)}</li>" for i in block.get("items", [])) + "</ol>"
    if kind == "formula":
        latex = block.get("latex") or text
        return f'<aside class="formula">\[{latex}\]</aside>'
    if kind == "figure":
        return render_figure(block, page_num, pages_rel)
    if kind == "table":
        return f'<pre class="table-text">{esc(text)}</pre>'
    if kind in {"caption", "footer"}:
        return f'<p class="{kind}">{esc(text)}</p>'
    return f"<p>{esc(text)}</p>" if text else ""


def render_page(page: dict[str, Any], pages_rel: str) -> str:
    page_num = int(page.get("page", 0))
    blocks = "
".join(render_block(b, page_num, pages_rel) for b in page.get("blocks", []))
    review = " needs-review" if page.get("quality", {}).get("needs_human_review") else ""
    return (
        f'<article class="page{review}" id="page-{page_num}">'
        f'<div class="page-meta"><span>Page {page_num}</span>'
        f'<span>{esc(page.get("running_footer",""))}</span></div>'
        f"{blocks}</article>"
    )


CSS = """:root{--paper:#fffdf7;--page:#fff;--ink:#111827;--muted:#64748b;--line:#d7dde7;--soft:#f8fafc;--accent:#0f766e}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif;font-size:18px;line-height:1.7}
.layout{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:100vh}
.toc{position:sticky;top:0;height:100vh;overflow:auto;padding:22px 16px;background:#f8fafc;border-right:1px solid var(--line)}
.toc h1{font-size:16px;margin:0 0 12px}
.toc a{display:block;padding:5px 8px;border-radius:6px;color:#334155;text-decoration:none;font-size:12px}
.toc a:hover{background:#eef6ff}
main{padding:36px 24px 80px}
.page{max-width:900px;margin:0 auto 28px;padding:46px 58px;background:var(--page);border:1px solid var(--line);box-shadow:0 16px 50px rgba(15,23,42,.07)}
.page.needs-review{border-left:5px solid #b45309}
.page-meta{display:flex;justify-content:space-between;margin-bottom:24px;padding-bottom:10px;border-bottom:1px solid var(--line);color:var(--muted);font-size:13px}
.chapter-title{font-size:44px;line-height:1.08;margin:0 0 24px}
h2{font-size:31px;margin:32px 0 12px}
h3{font-size:23px;margin:26px 0 8px}
p{margin:0 0 18px}
li{margin:7px 0}
.formula{margin:22px 0;padding:18px 20px;background:#ecfdf5;border-left:5px solid var(--accent);overflow-x:auto}
.figure{margin:28px 0;background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.scan-figure{border-color:#cbd5e1}
.page-scan{display:block;width:100%;height:auto}
figcaption{padding:10px 16px;text-align:center;font-size:14px;font-weight:650;color:#334155;background:#f8fafc;border-top:1px solid var(--line)}
.caption,.footer{color:var(--muted);font-size:14px}
.table-text{white-space:pre-wrap;background:#f8fafc;border:1px solid var(--line);padding:14px;border-radius:7px;font-size:15px}
@media(max-width:820px){.layout{display:block}.toc{position:relative;height:auto}.page{padding:28px 22px}.chapter-title{font-size:34px}}"""

KATEX_HEAD = (
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
'
    '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
'
    '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js" '
    'onload="renderMathInElement(document.body,{delimiters:['
    '{left:\'\\[\',right:\'\\]\',display:true},'
    '{left:\'\\(\',right:\'\\)\',display:false}'
    ']})"></script>'
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", help="Workspace directory")
    parser.add_argument("--output", help="Output HTML path (default: <workspace>/book.html)")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    ocr_dir = workspace / "ocr" / "pages"
    output = Path(args.output) if args.output else workspace / "book.html"

    pages = sorted(
        [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ocr_dir.glob("page_*.json"))],
        key=lambda d: d.get("page", 0),
    )
    if not pages:
        print(f"No OCR JSON found in {ocr_dir}")
        return

    # Relative path from the output HTML to the pages/ image directory
    pages_rel = os.path.relpath(workspace / "pages", output.parent)

    toc = "".join(f'<a href="#page-{p.get(\"page\")}">p.{p.get(\"page\")}</a>' for p in pages)
    body = "
".join(render_page(p, pages_rel) for p in pages)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f'<!doctype html><html lang="en"><head>'
        f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Book — OCR Rebuild</title>
{KATEX_HEAD}
<style>{CSS}</style></head><body>"
        f'<div class="layout"><aside class="toc"><h1>Pages</h1>{toc}</aside><main>{body}</main></div>'
        f"</body></html>",
        encoding="utf-8",
    )
    print(f"Built {len(pages)}-page HTML → {output}")


if __name__ == "__main__":
    main()
```

---

### 4. Run the pipeline

**Step 4a — Extract pages** (skip if `page_manifest.csv` already exists in workspace):
```bash
python3 <workspace>/scripts/extract.py "<pdf_path>" "<workspace>"
```

**Step 4b — Check which pages already have OCR** and report how many remain.

**Step 4c — Run OCR.** Use the correct provider flag:
```bash
python3 <workspace>/scripts/ocr.py "<workspace>" --provider openai --workers 3 --budget-usd 10
# or
python3 <workspace>/scripts/ocr.py "<workspace>" --provider anthropic --workers 3 --budget-usd 10
```

Tell the user the estimated cost before starting (pages remaining × ~$0.01 for GPT-4.1, ~$0.004 for Haiku, ~$0.016 for Sonnet).

**Step 4d — Retry failures.** After the run completes, identify pages that are in the manifest as `extracted` but have no OCR JSON. Re-run with `--only <comma-list>`.

**Step 4e — Build HTML:**
```bash
python3 <workspace>/scripts/build.py "<workspace>"
```

### 5. Report results

Tell the user:
- Total pages built
- Any pages still missing OCR
- Path to the output HTML
- Total estimated cost (sum from usage_log.jsonl if it exists)

---

## Provider model defaults

| Provider | Default model | Est. cost/page |
|----------|--------------|----------------|
| openai | gpt-4.1 | ~$0.010 |
| anthropic | claude-haiku-4-5-20251001 | ~$0.004 |

User can override with `--model` if they want Sonnet or gpt-4o.

## Notes

- All scripts are resumable: re-running skips already-done pages automatically.
- The `--budget-usd` flag is a safety cap — always recommend it on first runs.
- Pages with `no_image` status in the manifest are blank/non-image PDF pages — normal to skip.
- The figures directory (`<workspace>/figures/`) is optional — build.py works without it.
