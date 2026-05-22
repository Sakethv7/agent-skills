# agent-skills

A collection of skills for Claude Code and model-agnostic agents. Each skill is a
self-contained directory with a `SKILL.md` (Claude Code) and, where applicable, an
`AGENTS.md` (Codex, GPT-4o, any shell-capable agent).

## Skills

| Skill | What it does | Output |
|---|---|---|
| [scanned-doc-reader](./scanned-doc-reader/) | Convert a scanned PDF into study materials | STUDY_GUIDE.md, CONCEPTS.md, viewer.html (opt-in) |
| [paper-digest](./paper-digest/) | Digest an academic paper: methodology, results, limitations, open questions | DIGEST.md |
| [contract-extractor](./contract-extractor/) | Extract parties, dates, obligations, and flagged clauses from a legal document | CONTRACT_SUMMARY.md |
| [receipt-scanner](./receipt-scanner/) | Batch-extract expense data from scanned receipts into a CSV | expenses.csv, exceptions.txt |
| [whiteboard-to-notes](./whiteboard-to-notes/) | Convert a whiteboard photo or handwritten notes into structured markdown | NOTES.md |
| [slide-deck-reader](./slide-deck-reader/) | Extract the argument from a slide deck, not just the bullets | DECK_SUMMARY.md |

## Install (Claude Code)

Copy any `SKILL.md` into your Claude Code skills directory:

```bash
cp scanned-doc-reader/SKILL.md ~/.claude/skills/scanned-doc-reader.md
```

Then invoke with the skill name as a slash command, e.g. `/scanned-doc-reader`.

## Install (model-agnostic)

For skills with an `AGENTS.md`, place that file in your repo root or inject its
contents into your agent's system prompt. Works with OpenAI Codex, GPT-4o with
tools, and any agent that can run shell commands and Python.

## Dependencies

Most skills share the same stack:

```bash
# macOS
brew install poppler tesseract

# Ubuntu / Debian
sudo apt-get install poppler-utils tesseract-ocr
```

`whiteboard-to-notes` and vision-heavy paths use the language model's vision
capability directly — no tesseract needed.

## MCP server

[`doc-tools-mcp/`](./doc-tools-mcp/) is a Python MCP server that exposes the same
PDF and OCR operations as callable tools — for developers who want to integrate
document capabilities into their own agents rather than use the skill workflows.

```bash
# Run with uvx (no install needed)
uvx doc-tools-mcp

# Or install
pip install doc-tools-mcp
```

Add to Claude Desktop or Claude Code config:
```json
{ "mcpServers": { "doc-tools": { "command": "uvx", "args": ["doc-tools-mcp"] } } }
```

Tools exposed: `pdf_info`, `detect_text_layer`, `extract_text`, `ocr_pages`,
`rasterize_pages`, `extract_toc`.

---

## Adding a skill

Each skill directory needs at minimum a `SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-name
description: >
  One paragraph: what it does and when to trigger it.
---
```

See any existing skill for the full structure.
