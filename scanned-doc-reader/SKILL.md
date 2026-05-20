---
name: scanned-doc-reader
description: >
  Converts a scanned PDF into study materials: STUDY_GUIDE.md and CONCEPTS.md
  (always), plus an optional self-contained viewer.html with real OCR text and
  base64-encoded scan images. Use this skill whenever the user hands you a PDF
  that appears to be a scan, says "OCR this", "make a study guide from this book",
  "extract text from this PDF", or wants to turn any document — textbook, paper,
  manual — into structured study materials. If the user only wants raw text, skip
  the study outputs and just deliver the OCR. Viewer.html is opt-in — only
  generate it if the user asks.
---

# Scanned Doc Reader

## Outputs

- **STUDY_GUIDE.md** — chapter summaries, key points, study questions (always)
- **CONCEPTS.md** — core ideas, tradeoffs, diagrams (always)
- **viewer.html** — tabbed browser viewer with OCR text + real scan images (opt-in)

Ask the user upfront: "Do you want a browser viewer too, or just the markdown files?"

---

## Step 0 — Check dependencies

Before anything else, verify required tools exist:

```bash
for cmd in pdfinfo pdftotext pdftoppm tesseract python3; do
    command -v "$cmd" || echo "MISSING: $cmd"
done
```

If anything is missing:
- macOS: `brew install poppler tesseract`
- Ubuntu/Debian: `sudo apt-get install poppler-utils tesseract-ocr`

Stop and tell the user what to install before proceeding.

---

## Step 1 — Triage the PDF

Many "scanned" PDFs have an embedded text layer. Check first — it saves 5-10 minutes
of unnecessary OCR.

```bash
pdfinfo <file.pdf>
pdftotext <file.pdf> /tmp/text_check.txt
wc -c /tmp/text_check.txt
```

If the output is real text (> ~500 bytes, not garbage characters): **use it directly,
skip all OCR steps**. Go straight to Step 4.

If empty or garbled, confirm it's truly a scan:

```bash
pdftoppm -jpeg -r 72 -f 1 -l 1 <file.pdf> /tmp/confirm_scan
# inspect /tmp/confirm_scan-1.jpg
```

---

## Step 2 — Map structure, confirm chapters

Sample the TOC to understand the document before committing to OCR:

```bash
pdftoppm -jpeg -r 150 -f 1 -l 8 <file.pdf> /tmp/toc_pages
for img in /tmp/toc_pages-*.jpg; do
    tesseract "$img" stdout 2>/dev/null
done > /tmp/toc.txt
```

Read the output. Present the chapter list to the user:

> "I found these chapters: [list]. Which ones should I process?
>  (I'll OCR only those — full doc OCR is slow and usually unnecessary.)"

**Wait for the user to confirm before proceeding.**

---

## Step 3 — Selective OCR per chapter

For each confirmed chapter:

```bash
pdftoppm -jpeg -r 200 -f <start> -l <end> <file.pdf> /tmp/ch<N>_pages

for img in $(ls /tmp/ch<N>_pages-*.jpg | sort -V); do
    tesseract "$img" stdout 2>/dev/null >> /tmp/ch<N>_ocr.txt
done
```

One file per chapter: `/tmp/ch1_ocr.txt`, `/tmp/ch2_ocr.txt`, etc.
Keep the `.jpg` files if viewer.html was requested.

**Known OCR limitations** — warn the user if the document has:
- Two-column layout (tesseract reads across columns, mixing them)
- Math/equations (garbled output, use vision model instead)
- Tables (becomes jumbled text)
- Handwriting (tesseract cannot handle it; use vision model)
- Non-English text (re-run with `tesseract -l <lang>`)

---

## Step 4 — Generate study outputs

### STUDY_GUIDE.md

For each chapter, synthesize from the OCR text (not copy-paste — read and rewrite):

```markdown
# Study Guide: <Title>

## Chapter N: <Name>

**Summary**
3-5 sentences capturing the chapter's central argument, not just its topics.

**Key Points**
- ...

**Study Questions**
1. ...
```

Write study questions that require understanding, not just recall.

### CONCEPTS.md

Synthesize across all chapters — this is a cross-cutting view, not chapter-by-chapter:

```markdown
# Concepts: <Title>

## Core Ideas
<The 3-5 mental models the whole book is built on>

## Key Terms
- **Term**: one-line definition in context

## Tradeoffs
| Choice | Alternative | When to prefer this one |

## Architecture / Flow
<ASCII or Mermaid diagram if the material has structure worth visualizing>
```

### viewer.html (only if requested)

Write and run a Python script. Never hardcode chapter content or use placeholder
images — both bugs come from manual assembly. The script reads per-chapter OCR
files and base64-encodes real scan images at runtime.

```python
#!/usr/bin/env python3
import base64, glob, pathlib, re, sys

def build_viewer(output_path: str = "viewer.html") -> None:
    chapters = []
    for ocr_path in sorted(glob.glob("/tmp/ch*_ocr.txt")):
        n = re.search(r"ch(\d+)", ocr_path).group(1)
        text = pathlib.Path(ocr_path).read_text(errors="replace")
        imgs = []
        for img in sorted(
            glob.glob(f"/tmp/ch{n}_pages-*.jpg"),
            key=lambda p: int(re.search(r"-(\d+)\.jpg$", p).group(1))
        ):
            b64 = base64.b64encode(pathlib.Path(img).read_bytes()).decode()
            imgs.append(
                f'<img src="data:image/jpeg;base64,{b64}" '
                f'style="max-width:100%;display:block;margin:8px 0">'
            )
        chapters.append({"n": n, "text": text, "imgs": "\n".join(imgs)})

    nav = "".join(
        f'<button onclick="show({c["n"]})" id="btn{c["n"]}">Ch {c["n"]}</button>'
        for c in chapters
    )
    panels = "".join(f"""
        <div id="panel{c['n']}" class="panel" style="display:none">
          <div class="tabs">
            <button onclick="tab({c['n']},'text')">Text</button>
            <button onclick="tab({c['n']},'scan')">Scans</button>
          </div>
          <div id="text{c['n']}" class="tab-content">
            <pre style="white-space:pre-wrap;font-size:0.9em">{c['text']}</pre>
          </div>
          <div id="scan{c['n']}" class="tab-content" style="display:none">
            {c['imgs']}
          </div>
        </div>""" for c in chapters)

    first = chapters[0]["n"] if chapters else "1"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Study Viewer</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:960px;margin:0 auto;padding:16px}}
  button{{margin:4px;padding:6px 12px;cursor:pointer;border:1px solid #ccc;
          border-radius:4px;background:#f6f8fa}}
  .tab-content{{padding:12px;border:1px solid #ddd;border-radius:4px;margin-top:8px}}
</style></head><body>
<h1>Study Viewer</h1>
<div id="nav">{nav}</div>
<div id="content">{panels}</div>
<script>
function show(n){{
  document.querySelectorAll('.panel').forEach(p=>p.style.display='none');
  document.getElementById('panel'+n).style.display='block';
}}
function tab(n,which){{
  ['text','scan'].forEach(t=>{{
    document.getElementById(t+n).style.display=(t===which)?'block':'none';
  }});
}}
window.onload=()=>show({first});
</script></body></html>"""

    pathlib.Path(output_path).write_text(html)
    print(f"Written: {output_path}")

if __name__ == "__main__":
    build_viewer(sys.argv[1] if len(sys.argv) > 1 else "viewer.html")
```

Run: `python3 generate_viewer.py viewer.html`

Note: viewer.html can be large (50-100MB for image-heavy books). If the user needs
to share it, mention this upfront.

---

## Step 5 — Deliver

Report what was produced and where. If `present_files` is available, use it.

---

## Anti-patterns

| Avoid | Why |
|---|---|
| Calling `build_viewer_html()` without defining it | Undefined function — always use the complete script above |
| Hardcoding chapter text into HTML | All tabs show identical content |
| Placeholder `<img src="...">` instead of real base64 | Scan tab shows fake images |
| OCRing full document without asking | Slow, wasteful; user usually needs 2-4 chapters |
| Skipping `pdftotext` triage | Many "scanned" PDFs have text layers; OCR is unnecessary |
| Generating viewer.html by default | It's opt-in; always ask first |
