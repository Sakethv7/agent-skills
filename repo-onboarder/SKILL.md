---
name: repo-onboarder
description: >
  Map an unfamiliar codebase: entry points, data flow, key dependencies, and
  architecture decisions. Produces CODEBASE.md. Use this skill the first time
  you work in a repo, when a user says "get familiar with this codebase",
  "understand this project", "map out the architecture", "what does this repo do",
  or "where do I start". Also trigger when the user clones a new repo and asks
  any question about it — read the codebase first, answer second.
---

# Repo Onboarder

## Output: CODEBASE.md

A document a new engineer could read to understand the project in 10 minutes.

```markdown
# Codebase: <repo name>

## What this is
One paragraph: what the software does, who uses it, what problem it solves.

## How to run it
The minimum commands to get it running locally.

## Entry points
| File | Role |
|---|---|
| src/main.py | CLI entrypoint |
| src/app.py | Web server init |
| ... | ... |

## Architecture
Describe the major layers or components and how they relate.
Include an ASCII or Mermaid diagram if there's meaningful structure.

## Data flow
Trace the path of a typical request or operation end-to-end:
Input → [step] → [step] → Output

## Key modules / packages
| Path | Responsibility |
|---|---|
| src/auth/ | JWT validation and session management |
| ... | ... |

## External dependencies
| Dependency | Why it's here |
|---|---|
| httpx | Async HTTP client for downstream API calls |
| ... | ... |

## Config and environment
What env vars or config files does the project need? What are the defaults?

## Test strategy
Where are the tests? How do you run them? What's the coverage posture?

## Known rough edges
Anything that's messy, deprecated, under active refactor, or that a new
contributor would likely stumble on.

## Open questions
Things that weren't clear from reading the code — worth asking the team.
```

---

## Workflow

### Step 1 — Get oriented fast (parallel reads)

Run these together to build a quick mental model:

```bash
# Structure
find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.go" -o -name "*.rs" \) \
  | grep -v node_modules | grep -v .git | grep -v __pycache__ | sort | head -80

# Dependencies
cat pyproject.toml 2>/dev/null || cat requirements.txt 2>/dev/null || \
cat package.json 2>/dev/null || cat go.mod 2>/dev/null || cat Cargo.toml 2>/dev/null

# Existing docs
ls -1 *.md docs/ 2>/dev/null
cat README.md 2>/dev/null | head -100

# Git history — what's been worked on recently
git log --oneline -20

# Config / env
ls .env* *.yaml *.yml *.toml *.ini 2>/dev/null
```

### Step 2 — Find entry points

Look for the things that start the system:

```bash
# Python
grep -r "if __name__" --include="*.py" -l
grep -r "app = FastAPI\|app = Flask\|click.group\|typer.run" --include="*.py" -l

# TypeScript / Node
cat package.json | grep -E '"main"|"start"|"scripts"'
find . -name "index.ts" -o -name "main.ts" | grep -v node_modules

# Go
find . -name "main.go"

# Docker / compose
cat Dockerfile 2>/dev/null | grep ENTRYPOINT
cat docker-compose.yml 2>/dev/null | grep -A3 "command:"
```

### Step 3 — Trace a representative data flow

Pick the most common operation the software does and trace it through the codebase
by reading the relevant files. Don't read everything — follow the call chain.

For a web service: pick one API endpoint. Trace from route definition → handler →
business logic → data layer → response.

For a CLI tool: pick one command. Trace from argument parsing → execution → output.

For a data pipeline: trace one record from ingestion → transform → output.

### Step 4 — Read the tests

Tests are the most honest documentation. Look at:

```bash
find . -path "*/test*" -name "*.py" | head -20
find . -path "*__tests__*" -name "*.ts" | head -20
find . -name "*_test.go" | head -20
```

What scenarios do the tests cover? What's notably absent?

### Step 5 — Write CODEBASE.md

Fill in the template. Prioritize:
1. **Accuracy** over completeness — don't guess. If something is unclear, say so
   in "Open questions."
2. **The data flow section** — this is what new engineers actually need.
3. **Known rough edges** — what would have saved you time to know up front?

Save to the repo root (or `.claude/CODEBASE.md` if the root is too noisy).

### Step 6 — Deliver

Report the path. If `present_files` is available, use it.

---

## What makes a good CODEBASE.md

**Bad:** A directory listing with one-line descriptions of every file.

**Good:** A document that explains *why* the code is structured the way it is —
what decisions were made, what tradeoffs exist, and what the code is actually doing
at a conceptual level.

The data flow section is the most valuable — architecture diagrams lie, data flows
don't.
