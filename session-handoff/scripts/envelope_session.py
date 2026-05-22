#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "session-handoff"


# ── inline markdown → HTML ────────────────────────────────────────────────────

def _inline(text: str) -> str:
    """Process inline code spans first, then bold/italic/links on remaining text."""
    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"`([^`]+)`", text):
        if m.start() > pos:
            parts.append(_spans(text[pos : m.start()]))
        parts.append(f"<code>{html.escape(m.group(1))}</code>")
        pos = m.end()
    if pos < len(text):
        parts.append(_spans(text[pos:]))
    return "".join(parts)


def _spans(text: str) -> str:
    """Bold, italic, and links — extracted before HTML-escaping plain text."""
    pattern = re.compile(
        r"(\[(?P<lt>[^\]]*)\]\((?P<lh>[^)]*)\))"  # [label](url)
        r"|(\*\*(?P<bt>[^*]+)\*\*)"                # **bold**
        r"|(\*(?P<it>[^*]+)\*)"                    # *italic*
    )
    out: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            out.append(html.escape(text[last : m.start()]))
        if m.group("lt") is not None:
            lt = html.escape(m.group("lt"))
            lh = html.escape(m.group("lh"))
            out.append(f'<a href="{lh}">{lt}</a>')
        elif m.group("bt") is not None:
            out.append(f"<strong>{html.escape(m.group('bt'))}</strong>")
        else:
            out.append(f"<em>{html.escape(m.group('it'))}</em>")
        last = m.end()
    if last < len(text):
        out.append(html.escape(text[last:]))
    return "".join(out)


# ── block-level markdown → HTML ───────────────────────────────────────────────

def markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        if stripped.startswith("```"):
            close_lists()
            lang = html.escape(stripped[3:].strip())
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code_body = html.escape("\n".join(code_lines))
            cls = f' class="language-{lang}"' if lang else ""
            parts.append(f"<pre><code{cls}>{code_body}</code></pre>")
            continue

        # ATX heading
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            close_lists()
            level = len(m.group(1))
            parts.append(f"<h{level}>{_inline(m.group(2).rstrip('#').strip())}</h{level}>")
            i += 1
            continue

        # Horizontal rule (checked before list items so --- isn't treated as a list)
        if re.match(r"^(-{3,}|_{3,}|\*{3,})\s*$", stripped) and stripped:
            close_lists()
            parts.append("<hr>")
            i += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            close_lists()
            bq_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                bq_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            inner = markdown_to_html("\n".join(bq_lines))
            parts.append(f"<blockquote>{inner}</blockquote>")
            continue

        # Unordered list item
        m = re.match(r"^[*\-]\s+(.*)", line)
        if m:
            if in_ol:
                parts.append("</ol>")
                in_ol = False
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"  <li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # Ordered list item
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if not in_ol:
                parts.append("<ol>")
                in_ol = True
            parts.append(f"  <li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # Blank line
        if not stripped:
            close_lists()
            parts.append("")
            i += 1
            continue

        # Paragraph — collect consecutive non-structural lines
        close_lists()
        para_lines: list[str] = []
        while i < len(lines):
            l = lines[i]
            s = l.strip()
            if not s:
                break
            if (
                re.match(r"^#{1,6}\s", l)
                or s.startswith("```")
                or re.match(r"^(-{3,}|_{3,}|\*{3,})\s*$", s)
                or re.match(r"^[*\-]\s", l)
                or re.match(r"^\d+\.\s", l)
            ):
                break
            para_lines.append(l)
            i += 1
        if para_lines:
            parts.append(f"<p>{_inline(' '.join(para_lines))}</p>")

    close_lists()
    return "\n".join(parts)


# ── HTML shell ────────────────────────────────────────────────────────────────

def render_html(markdown_text: str, title: str) -> str:
    body = markdown_to_html(markdown_text)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      max-width: 860px;
      margin: 48px auto;
      padding: 0 20px;
      line-height: 1.65;
      color: #1a1a1a;
    }}
    h1, h2, h3, h4, h5, h6 {{ margin-top: 1.5em; margin-bottom: 0.4em; line-height: 1.25; }}
    h1 {{ font-size: 1.9em; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.3em; }}
    h2 {{ font-size: 1.4em; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.2em; }}
    pre {{
      background: #f6f8fa;
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      padding: 14px 16px;
      overflow-x: auto;
      font-size: 0.88em;
    }}
    code {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }}
    p > code, li > code {{
      background: #f0f0f0;
      padding: 2px 5px;
      border-radius: 3px;
      font-size: 0.9em;
    }}
    ul, ol {{ padding-left: 1.6em; }}
    li {{ margin: 0.3em 0; }}
    hr {{ border: none; border-top: 1px solid #d0d0d0; margin: 1.8em 0; }}
    a {{ color: #0969da; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    blockquote {{
      margin: 1em 0;
      padding: 0.4em 1em;
      border-left: 4px solid #d0d7de;
      color: #57606a;
    }}
    blockquote p {{ margin: 0.3em 0; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


# ── main ─────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate session handoff in both Markdown and HTML")
    parser.add_argument(
        "--input", required=True,
        help="Path to source markdown/text file, or - to read from stdin",
    )
    parser.add_argument("--title", default="Session Handoff", help="Handoff title")
    parser.add_argument("--outdir", required=True, help="Output directory (created if absent)")
    parser.add_argument(
        "--resume-prompt", action="store_true",
        help="Append a resume-prompt footer to the .md output",
    )
    parser.add_argument(
        "--open", action="store_true",
        help="Open the HTML file in the default browser after generation",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.input == "-":
        md_text = sys.stdin.read()
    else:
        source = Path(args.input)
        if not source.is_file():
            raise SystemExit(f"Input file not found: {source}")
        md_text = source.read_text(encoding="utf-8")

    if args.resume_prompt:
        md_text = md_text.rstrip("\n") + (
            "\n\n---\n\n"
            "**To resume:** paste this document as context at the start of your next session.\n"
        )

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    slug = slugify(args.title)

    md_path = outdir / f"{slug}_{ts}.md"
    html_path = outdir / f"{slug}_{ts}.html"

    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(render_html(md_text, args.title), encoding="utf-8")

    print(str(md_path))
    print(str(html_path))

    if args.open:
        import webbrowser
        webbrowser.open(html_path.as_uri())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
