---
name: env-doctor
description: >
  Check that a project's environment is correctly set up: dependencies installed,
  env vars present, config files valid, services reachable. Produces HEALTH.md.
  Use this skill at the start of any project session, when the user says "check
  if this is set up correctly", "why isn't this running", "is my environment
  right", "set up check", or before starting a task in an unfamiliar project.
  Run proactively when a repo is cloned or a new dev environment is described.
---

# Env Doctor

## Output: HEALTH.md

```markdown
# Environment Health: <project name>

**Checked:** <timestamp>
**Overall status:** HEALTHY | DEGRADED | BROKEN

## Summary
One line per check: ✅ PASS, ⚠️ WARN, ❌ FAIL

## Runtime
- Python / Node / Go version: ...
- Expected: ...
- Status: ✅ / ❌

## Dependencies
- All required packages installed: ✅ / ❌
- Missing: [list]
- Version mismatches: [list]

## Environment variables
| Variable | Status | Notes |
|---|---|---|
| DATABASE_URL | ✅ set | — |
| OPENAI_API_KEY | ⚠️ set but looks wrong | Doesn't match expected format |
| SECRET_KEY | ❌ missing | Required for auth to work |

## Config files
| File | Status | Issue |
|---|---|---|
| .env | ✅ present | — |
| config/settings.yaml | ⚠️ present | `db.host` is localhost — ok for dev |
| .env.production | ❌ missing | — |

## Services and connectivity
| Service | Status | Notes |
|---|---|---|
| PostgreSQL (localhost:5432) | ✅ reachable | — |
| Redis (localhost:6379) | ❌ unreachable | Not running? |
| External API (api.stripe.com) | ✅ reachable | — |

## Recommended fixes
Ordered by severity:
1. ❌ Set `SECRET_KEY` in .env — auth will not work without it
2. ❌ Start Redis: `docker compose up redis -d`
3. ⚠️ ...
```

---

## Workflow

### Step 1 — Identify what this project expects

```bash
# Language runtime
cat .python-version 2>/dev/null || cat .nvmrc 2>/dev/null || \
cat .tool-versions 2>/dev/null || cat go.mod 2>/dev/null | head -5

# Dependency manifest
cat pyproject.toml 2>/dev/null
cat requirements.txt 2>/dev/null
cat package.json 2>/dev/null
cat go.mod 2>/dev/null

# Env var expectations
cat .env.example 2>/dev/null || cat .env.sample 2>/dev/null
grep -r "os.environ\|os.getenv\|process.env\|viper.Get" \
  --include="*.py" --include="*.ts" --include="*.go" -h \
  | grep -oP '(?<=getenv\(")[^"]+|(?<=environ\[")[^"]+' | sort -u

# Config files
ls -1 .env* *.yaml *.yml *.toml *.ini config/ 2>/dev/null
```

### Step 2 — Check runtime versions

```bash
python3 --version 2>/dev/null
node --version 2>/dev/null
go version 2>/dev/null
ruby --version 2>/dev/null

# Compare against expected
# Flag if minor version mismatch (warn), major version mismatch (fail)
```

### Step 3 — Check dependencies

**Python:**
```bash
pip check                          # detects conflicts
pip list --not-required 2>/dev/null | head -20
python3 -c "import pkg_resources; pkg_resources.require(open('requirements.txt').readlines())" 2>&1
```

**Node:**
```bash
npm ls --depth=0 2>&1 | grep "UNMET\|missing\|invalid" || echo "OK"
```

**Go:**
```bash
go mod verify 2>&1
```

### Step 4 — Check environment variables

Compare what's in `.env.example` (or grep'd from code) against what's actually set:

```bash
# What's set
env | grep -E "DATABASE|API_KEY|SECRET|TOKEN|URL|HOST|PORT" | sort

# What's in .env (if readable)
cat .env 2>/dev/null | grep -v "^#" | grep -v "^$"
```

For each expected variable:
- ❌ FAIL if missing and required
- ⚠️ WARN if present but value looks wrong (empty, contains placeholder like
  `your_key_here`, wrong format for the type — e.g. a DATABASE_URL that doesn't
  start with `postgresql://`)
- ✅ PASS if present and format looks right (don't log the actual value)

### Step 5 — Check service connectivity

```bash
# PostgreSQL
pg_isready -h localhost -p 5432 2>/dev/null && echo "PG: OK" || echo "PG: FAIL"

# Redis
redis-cli ping 2>/dev/null && echo "Redis: OK" || echo "Redis: FAIL"

# Generic TCP check
python3 -c "import socket; s=socket.create_connection(('localhost', 8080), 2); print('OK')" 2>/dev/null

# External HTTP
curl -sf --max-time 3 https://api.example.com/health 2>/dev/null && echo "OK" || echo "FAIL"
```

Only check services that the project actually uses (inferred from config/env vars).

### Step 6 — Write HEALTH.md and recommend fixes

Order recommendations by impact:
1. Anything that makes the app completely non-functional (❌)
2. Anything that will cause runtime errors in specific paths (⚠️ with known impact)
3. Configuration that's suboptimal but won't break things (⚠️ minor)

Include the exact command to fix each issue where possible.

### Step 7 — Deliver

Report overall status at the top. If `present_files` is available, use it.

---

## Security note

Never log actual secret values in HEALTH.md. Log only whether variables are set
and whether their format looks correct. Use `***` or `[set]` as placeholders.
