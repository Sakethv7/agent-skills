# agent-skills

Skills and MCP servers for Claude Code and model-agnostic agents. Each skill is a
self-contained workflow; each MCP exposes reusable tools any agent can call mid-task.

---

## Skills

Install any skill by copying its `SKILL.md` to `~/.claude/skills/<name>.md` and
invoking with `/<name>` in Claude Code.

| Skill | What it does | Output |
|---|---|---|
| [scanned-doc-reader](./scanned-doc-reader/) | Scanned PDF → study materials via selective OCR | STUDY_GUIDE.md, CONCEPTS.md, viewer.html (opt-in) |
| [paper-digest](./paper-digest/) | Academic paper → methodology, results, limitations, open questions | DIGEST.md |
| [contract-extractor](./contract-extractor/) | Legal doc → parties, dates, obligations, flagged clauses | CONTRACT_SUMMARY.md |
| [receipt-scanner](./receipt-scanner/) | Scanned receipts → expense CSV | expenses.csv, exceptions.txt |
| [whiteboard-to-notes](./whiteboard-to-notes/) | Whiteboard photo → structured markdown (vision, not OCR) | NOTES.md |
| [slide-deck-reader](./slide-deck-reader/) | Slide deck → argument extraction, not just bullet list | DECK_SUMMARY.md |
| [repo-onboarder](./repo-onboarder/) | New codebase → entry points, data flow, architecture map | CODEBASE.md |
| [debug-trail](./debug-trail/) | Live debug session capture: hypothesis → test → result → conclusion | DEBUG_TRAIL.md |
| [data-profiler](./data-profiler/) | Any file (CSV, Excel, PPTX, DOCX, PDF) → insights, patterns, what it means | INSIGHTS.md |
| [env-doctor](./env-doctor/) | Check deps, env vars, config, and service connectivity | HEALTH.md |

---

## MCP Servers

Add any MCP to Claude Code or Claude Desktop via `settings.json`:

```json
{
  "mcpServers": {
    "doc-tools":        { "command": "uvx", "args": ["doc-tools-mcp"] },
    "notebook-runner":  { "command": "uvx", "args": ["notebook-runner-mcp"] },
    "git-context":      { "command": "uvx", "args": ["git-context-mcp"] },
    "data-tools":       { "command": "uvx", "args": ["data-tools-mcp"] }
  }
}
```

| MCP | Tools | Dependencies |
|---|---|---|
| [doc-tools-mcp](./doc-tools-mcp/) | `pdf_info`, `detect_text_layer`, `extract_text`, `ocr_pages`, `rasterize_pages`, `extract_toc` | poppler, tesseract |
| [notebook-runner-mcp](./notebook-runner-mcp/) | `get_notebook_info`, `list_cells`, `get_cell`, `run_cell`, `run_all`, `run_range`, `insert_cell`, `update_cell`, `delete_cell`, `clear_outputs`, `get_errors`, `get_variables`, `export_to_script` | nbformat, nbconvert, jupyter_client |
| [git-context-mcp](./git-context-mcp/) | `git_status`, `git_log`, `git_diff`, `git_blame`, `list_branches`, `create_branch`, `checkout`, `stash`, `pr_list`, `pr_view`, `pr_diff`, `pr_create`, `pr_comment`, `pr_merge`, `pr_checks`, `mr_list`, `mr_view`, `mr_create` | gh CLI (GitHub), glab CLI (GitLab) |
| [data-tools-mcp](./data-tools-mcp/) | `profile_file`, `list_sheets`, `sample_file`, `find_column_in_file`, `compare_schemas`, `list_tables`, `describe_table`, `sample_rows`, `find_column`, `run_query` | pandas, openpyxl, sqlalchemy, pyarrow |

---

## Skills vs MCPs

**Skills** are workflow templates — multi-step processes with user confirmation
gates. Use them when you want guided, interactive document processing.

**MCPs** expose raw tools any agent can call mid-task without an explicit workflow.
Use them when you need PDF/notebook/git/data capabilities composable with other work.

They complement each other: the document skills use `doc-tools-mcp` under the hood
when it's connected.

---

## Install

```bash
# Skills — copy to Claude Code skills dir
cp repo-onboarder/SKILL.md ~/.claude/skills/repo-onboarder.md

# MCPs — install and configure
pip install doc-tools-mcp notebook-runner-mcp git-context-mcp data-tools-mcp
# or run without installing: uvx <package-name>
```

### System dependencies

```bash
# macOS (for doc-tools)
brew install poppler tesseract

# Ubuntu/Debian
sudo apt-get install poppler-utils tesseract-ocr

# GitHub ops (git-context-mcp)
brew install gh && gh auth login

# GitLab ops (git-context-mcp)
brew install glab && glab auth login
```

---

## Adding a skill

Each skill directory needs a `SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-name
description: >
  What it does and when to trigger it.
---
```
