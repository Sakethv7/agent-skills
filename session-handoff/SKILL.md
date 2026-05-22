---
name: session-handoff
description: >
  Capture the current session's full context — conversation, files changed,
  commands run, decisions made — and emit a .md + rendered .html handoff.
  Works in Claude Code (saves files locally) and claude.ai chat (generates
  downloadable artifacts). Zero configuration. Works in any project.
triggers:
  - /session-handoff
  - session handoff
  - save session
  - export session context
  - create handoff
  - handoff
---

# Session Handoff Skill

Packages the active session into two outputs:
- **`.md`** — structured context, pasteable into a new thread to resume
- **`.html`** — styled, browser-ready page for sharing with teammates

---

## Detect environment first

Before anything else, determine which mode to use:

- **Claude Code mode** — bash tools are available (`Bash`, `Write`, etc.)
- **Chat mode** — no bash tools (claude.ai, Claude desktop app chat)

Proceed to the matching section below.

---

## Step 1 — Synthesize session context (both modes)

Extract from the current conversation. Be dense and specific. Omit empty sections.

```markdown
# {title}

**Date:** {YYYY-MM-DD}
**Project:** {repo name or topic}
**Branch:** {git branch if available, else omit}
**Status:** {one sentence — what state is the work in right now}

## What was done

- {specific completed items — file paths, function names, test results}

## Key decisions

{One paragraph per decision: what was chosen · what the alternative was · why.}

## Files changed

| File | Change |
|------|--------|
| `path/to/file` | what changed |

## Commands run

```bash
# key commands with meaningful side effects
```

## Constraints

1. {hard limits that must stay true — omit if none}

## Open questions

- {unresolved items — omit if none}

## Next action

{Single most important next step. Must be immediately executable —
a real command, file to open, or PR to create. Not "continue working on X."}

---

**To resume:** paste this document as context at the start of your next session.
```

Rules:
- Infer `{title}` from the session topic. Do not ask the user.
- "Next action" must be a real command or step, not a vague description.
- Keep the document under 500 words.

---

## Claude Code mode

*Use this path when bash tools are available.*

**Gather additional facts from git:**

```bash
git status --short 2>/dev/null || true
git log --oneline -10 2>/dev/null || true
git diff --stat HEAD 2>/dev/null || true
```

**Ensure the script is available:**

```bash
# Check locally first
ls scripts/envelope_session.py 2>/dev/null \
  || ls ~/.claude/scripts/envelope_session.py 2>/dev/null \
  || (mkdir -p ~/.claude/scripts && curl -fsSL \
      https://raw.githubusercontent.com/Sakethv7/agent-skills/main/session-handoff/scripts/envelope_session.py \
      -o ~/.claude/scripts/envelope_session.py)
```

**Write the handoff and run the script:**

```bash
# Write synthesized content to temp file
# (use the Write tool for the actual file write)

python3 {script_path} \
  --input /tmp/handoff_{slug}_{ts}.md \
  --title "{title}" \
  --outdir ~/handoffs \
  --resume-prompt \
  --open
```

Outputs go to `~/handoffs/` — never committed to git.

**Report:**

```
Session handoff saved:

  .md   → ~/handoffs/{slug}_{ts}.md
  .html → ~/handoffs/{slug}_{ts}.html

To resume: paste the .md at the top of a new session.
```

---

## Chat mode

*Use this path in claude.ai chat or the Claude desktop app when bash is not available.*

Generate two artifacts directly in the conversation:

### Artifact 1 — Markdown

Create an artifact of type `text/markdown` titled `{title}.md` containing the
synthesized handoff document from Step 1. The user can copy or download it.

### Artifact 2 — HTML

Create an artifact of type `text/html` titled `{title}.html` containing the
fully self-contained rendered HTML below. Replace `{RENDERED_BODY}` with the
handoff content converted to HTML, and `{TITLE}` with the session title.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{TITLE}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      max-width: 860px; margin: 48px auto; padding: 0 20px;
      line-height: 1.65; color: #1a1a1a;
    }
    h1, h2, h3 { margin-top: 1.5em; margin-bottom: 0.4em; line-height: 1.25; }
    h1 { font-size: 1.9em; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.3em; }
    h2 { font-size: 1.4em; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.2em; }
    pre { background: #f6f8fa; border: 1px solid #e0e0e0; border-radius: 6px;
          padding: 14px 16px; overflow-x: auto; font-size: 0.88em; }
    code { font-family: "SFMono-Regular", Consolas, Menlo, monospace; }
    p > code, li > code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; }
    ul, ol { padding-left: 1.6em; } li { margin: 0.3em 0; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }
    th { background: #f6f8fa; font-weight: 600; }
    blockquote { margin: 1em 0; padding: 0.4em 1em; border-left: 4px solid #d0d7de; color: #57606a; }
    hr { border: none; border-top: 1px solid #d0d0d0; margin: 1.8em 0; }
    a { color: #0969da; text-decoration: none; } a:hover { text-decoration: underline; }
  </style>
</head>
<body>
{RENDERED_BODY}
</body>
</html>
```

When rendering `{RENDERED_BODY}`, convert the markdown to HTML:
- `# heading` → `<h1>`, `## heading` → `<h2>`, etc.
- `**bold**` → `<strong>`, `*italic*` → `<em>`
- `` `code` `` → `<code>`
- ` ```lang ... ``` ` → `<pre><code class="language-lang">...</code></pre>`
- `- item` / `* item` → `<ul><li>`
- `1. item` → `<ol><li>`
- `> text` → `<blockquote>`
- `---` → `<hr>`
- `[text](url)` → `<a href="url">text</a>`
- Blank line between text → new `<p>` block
- HTML-escape all content (`<`, `>`, `&`) before inserting

**Report:**

```
Session handoff ready:

  .md   — see artifact "{title}.md" above (copy or download)
  .html — see artifact "{title}.html" above (preview or download)

To resume: paste the .md content at the top of a new session.
```

---

## Rules (both modes)

- Never ask the user to provide content. Derive everything from the session.
- If git is unavailable, skip branch/files-changed gracefully.
- "Next action" must be a concrete command or step — not "continue working on X."
- Outputs are local/artifacts only — never committed to any git repo.
