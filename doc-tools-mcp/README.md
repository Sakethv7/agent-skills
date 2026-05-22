# doc-tools-mcp

MCP server that exposes PDF text extraction and OCR as callable tools. Drop it into
any MCP-compatible agent (Claude Code, Claude Desktop, GPT-4o, custom agents) and
the agent can extract text, OCR pages, rasterize images, and parse TOCs without
running shell commands itself.

## Tools

| Tool | What it does |
|---|---|
| `pdf_info` | Metadata: page count, title, author, file size, encryption status |
| `detect_text_layer` | Check if the PDF has a usable embedded text layer (call this first) |
| `extract_text` | Extract text via native text layer — fast and accurate |
| `ocr_pages` | OCR a page range using pdftoppm + tesseract — for true scans |
| `rasterize_pages` | Convert pages to base64 JPEG images for vision models or HTML viewers |
| `extract_toc` | Parse the table of contents, with OCR fallback |

**Always call `detect_text_layer` first.** Many "scanned" PDFs have embedded text
layers. `extract_text` is 10-50x faster and more accurate than `ocr_pages`.

## System dependencies

```bash
# macOS
brew install poppler tesseract

# Ubuntu / Debian
sudo apt-get install poppler-utils tesseract-ocr
```

## Install

```bash
pip install doc-tools-mcp
# or, with uv:
uv pip install doc-tools-mcp
```

Or run directly without installing:
```bash
uvx doc-tools-mcp
```

## Configure

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "doc-tools": {
      "command": "uvx",
      "args": ["doc-tools-mcp"]
    }
  }
}
```

### Claude Code (`.claude/settings.json` or global `~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "doc-tools": {
      "command": "uvx",
      "args": ["doc-tools-mcp"]
    }
  }
}
```

### Any MCP-compatible agent

Point the agent at the `doc-tools-mcp` entry point. The server speaks the standard
MCP protocol over stdio.

## Usage example

Once connected, the agent can call tools directly:

```
# Agent flow for a scanned PDF:
1. pdf_info(path)             → confirm page count
2. detect_text_layer(path)    → has_text_layer: false → proceed to OCR
3. extract_toc(path)          → get chapter list, confirm with user
4. ocr_pages(path, 12, 45)   → OCR chapter 2
5. ocr_pages(path, 46, 78)   → OCR chapter 3

# Agent flow for a digital PDF:
1. detect_text_layer(path)    → has_text_layer: true → use extract_text
2. extract_text(path, 1, 50)  → fast full extraction
```

## Relation to the skills in this repo

The [skills](../) in this repo (`scanned-doc-reader`, `paper-digest`, etc.) are
workflow templates that guide an agent through multi-step document processing with
user confirmation gates. This MCP provides the *underlying tools* those workflows
use — and makes them available to any task, not just the explicit workflow invocations.

They compose: use the skills for guided workflows, use the MCP tools when you need
raw PDF capabilities mid-task.

## Development

```bash
git clone https://github.com/Sakethv7/agent-skills
cd agent-skills/doc-tools-mcp
pip install -e ".[dev]"
python -m doc_tools.server   # run locally
```
