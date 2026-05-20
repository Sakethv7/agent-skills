# Scanned Doc Reader — Agent Instructions

Model-agnostic playbook for converting scanned PDFs into structured study materials.
Compatible with Claude Code, OpenAI Codex, GPT-4o with tools, and any agent that
can execute shell commands and write files.

## Trigger conditions

Use this playbook when the user:
- Provides a PDF and asks for a study guide, notes, or summary
- Asks to "OCR" a file or extract text from a scanned document
- Wants a textbook, paper, or manual turned into study materials
- Mentions `pdftotext` returning empty/garbled output

## Outputs

| File | When |
|---|---|
| `STUDY_GUIDE.md` | Always |
| `CONCEPTS.md` | Always |
| `viewer.html` | **Opt-in only** — ask the user before generating |

Ask upfront: "Do you want a browser viewer too, or just the markdown files?"
Viewer.html can be 50-100MB for image-heavy books — mention this if they say yes.

---

## Required tools / dependencies

```
pdfinfo       # from poppler-utils
pdftotext     # from poppler-utils
pdftoppm      # from poppler-utils
tesseract     # tesseract-ocr
python3       # for HTML generation
```

Install on Ubuntu/Debian: `sudo apt-get install poppler-utils tesseract-ocr`
Install on macOS: `brew install poppler tesseract`

---

## Phase 0 — Triage

```bash
pdfinfo "$PDF"
pdftotext "$PDF" /tmp/text_check.txt
wc -c /tmp/text_check.txt
```

**Decision:**
- If `/tmp/text_check.txt` contains real text (> ~500 bytes, not garbage): use it
  directly. Skip all OCR. The PDF has a text layer.
- If output is empty or garbled: proceed to Phase 1.

Quick visual confirm (optional but recommended):
```bash
pdftoppm -jpeg -r 72 -f 1 -l 1 "$PDF" /tmp/confirm_scan
# Inspect /tmp/confirm_scan-1.jpg to verify it is truly a scanned page
```

---

## Phase 1 — Structure mapping

Sample the front matter and table of contents:

```bash
# Front matter
pdftoppm -jpeg -r 120 -f 1 -l 3 "$PDF" /tmp/frontmatter
tesseract /tmp/frontmatter-1.jpg stdout > /tmp/frontmatter.txt

# TOC area (adjust page range to match the document)
pdftoppm -jpeg -r 150 -f 4 -l 8 "$PDF" /tmp/toc
for f in /tmp/toc-*.jpg; do tesseract "$f" stdout; done > /tmp/toc.txt
```

Read `/tmp/toc.txt`. Present the chapter list to the user and ask which chapters
to process. **Do not proceed until the user confirms.** This prevents unnecessary
processing of unwanted chapters.

Example prompt to user:
> "I found these chapters: [list with page ranges]. Which ones should I OCR?
>  Processing all 12 chapters will take ~8 minutes; selective processing is faster."

---

## Phase 2 — Selective OCR

For each confirmed chapter (replace `START`, `END`, `N` with actual values):

```bash
# Rasterize at 200 DPI
pdftoppm -jpeg -r 200 -f $START -l $END "$PDF" /tmp/ch${N}_pages

# OCR each page, concatenate into per-chapter file
> /tmp/ch${N}_ocr.txt
for img in $(ls /tmp/ch${N}_pages-*.jpg | sort -V); do
    tesseract "$img" stdout 2>/dev/null >> /tmp/ch${N}_ocr.txt
done
```

Result: `/tmp/ch1_ocr.txt`, `/tmp/ch2_ocr.txt`, … — one file per chapter.
Keep the `.jpg` rasterizations; they are needed for the viewer.

---

## Phase 3 — Generate outputs

### Rule: always generate viewer.html programmatically

Never write HTML by hand with chapter content copy-pasted in. Always use a script
that reads the OCR text files and encodes the real scan images. Manual approaches
cause two silent bugs:
1. All chapter tabs show the same text (copy-paste error)
2. Scan tab shows placeholder images instead of real document pages

### viewer.html generation script

```python
#!/usr/bin/env python3
"""Generate self-contained viewer.html from per-chapter OCR files and scan images."""
import base64, glob, pathlib, re, sys

def build_viewer(output_path: str = "viewer.html") -> None:
    chapters = []
    for ocr_path in sorted(glob.glob("/tmp/ch*_ocr.txt")):
        n = re.search(r"ch(\d+)", ocr_path).group(1)
        text = pathlib.Path(ocr_path).read_text(errors="replace")
        imgs = []
        for img in sorted(glob.glob(f"/tmp/ch{n}_pages-*.jpg"),
                          key=lambda p: int(re.search(r"-(\d+)\.jpg$", p).group(1))):
            b64 = base64.b64encode(pathlib.Path(img).read_bytes()).decode()
            imgs.append(f'<img src="data:image/jpeg;base64,{b64}" '
                        f'style="max-width:100%;display:block;margin:8px 0">')
        chapters.append({"n": n, "text": text, "imgs": "\n".join(imgs)})

    nav = "".join(
        f'<button onclick="show({c["n"]})" id="btn{c["n"]}">Ch {c["n"]}</button>'
        for c in chapters
    )
    panels = "".join(f"""
        <div id="panel{c['n']}" class="panel" style="display:none">
          <div class="tabs">
            <button onclick="tab({c['n']},'text')" id="t{c['n']}text">Text</button>
            <button onclick="tab({c['n']},'scan')" id="t{c['n']}scan">Scans</button>
          </div>
          <div id="text{c['n']}" class="tab-content">
            <pre style="white-space:pre-wrap;font-size:0.9em">{c['text']}</pre>
          </div>
          <div id="scan{c['n']}" class="tab-content" style="display:none">
            {c['imgs']}
          </div>
        </div>""" for c in chapters)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Study Viewer</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:960px;margin:0 auto;padding:16px}}
  button{{margin:4px;padding:6px 12px;cursor:pointer}}
  .tab-content{{padding:12px;border:1px solid #ddd;border-radius:4px}}
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
// Show first chapter on load
window.onload=()=>show({chapters[0]['n'] if chapters else 1});
</script></body></html>"""

    pathlib.Path(output_path).write_text(html)
    print(f"Written: {output_path}")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "viewer.html"
    build_viewer(out)
```

Run it: `python3 generate_viewer.py viewer.html`

### STUDY_GUIDE.md structure

```markdown
# Study Guide: <Book Title>

## Chapter N: <Title>

**Summary**
3-5 sentence narrative summary of the chapter's main argument.

**Key Points**
- Point 1
- Point 2
...

**Study Questions**
1. Question 1?
2. Question 2?
...
```

Produce this section for each OCR'd chapter.

### CONCEPTS.md structure

```markdown
# Concepts: <Book Title>

## Core Ideas
<Synthesized across all chapters — the central mental models>

## Key Terms
- **Term**: definition

## Tradeoffs
| Option A | Option B | When to prefer A |
|---|---|---|

## Architecture / Flow
<ASCII or Mermaid diagram if the material has a structural component>
```

---

## Phase 4 — Deliver

Report file locations to the user:

```
Outputs:
  viewer.html     — open in browser, tab per chapter (text + scan images)
  STUDY_GUIDE.md  — summaries and study questions
  CONCEPTS.md     — key ideas and tradeoffs
```

If the agent framework has a file-delivery primitive (e.g., `present_files`,
`artifacts`, file attachment), use it. Otherwise report the absolute paths.

---

## Common failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| All chapters show same OCR text in viewer | Content hardcoded, not read from per-chapter files | Regenerate viewer.html via the Python script |
| Scan tab shows no images or placeholders | Images not base64-encoded into HTML | Re-run script; verify `/tmp/ch*_pages-*.jpg` exist |
| `tesseract: command not found` | Dependency missing | `brew install tesseract` or `apt-get install tesseract-ocr` |
| `pdftoppm` produces blank images | PDF is DRM-protected | Inform user; no workaround without authorization |
| OCR text is garbage characters | Wrong language pack | `tesseract --list-langs`; re-run with `-l <lang>` |
| pdftotext returns good text but you still ran OCR | Skipped Phase 0 triage | Always check text layer first |

---

## Compatibility notes

This playbook is tested with:
- **Claude Code** (use as SKILL.md — see `SKILL.md` in this repo)
- **OpenAI Codex / GPT-4o with tools** (place AGENTS.md in repo root)
- **Any agent** with shell execution and Python 3.8+

For Claude Code: install `SKILL.md` as a skill and invoke with `/scanned-doc-reader`.
For Codex/other: reference this file in your system prompt or agent instructions.
