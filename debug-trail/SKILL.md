---
name: debug-trail
description: >
  Maintain a running DEBUG_TRAIL.md that captures each debugging step as it
  happens: hypothesis, test, result, and conclusion. Use this skill when the
  user says "start a debug trail", "log this debug session", "track what we're
  trying", or when a debugging session starts and you want to preserve the
  reasoning for later. Also invoke automatically at the start of any non-trivial
  bug investigation so the trail is always there when needed. Append to the trail
  throughout the session — don't wait until the end.
---

# Debug Trail

The core idea: debugging sessions produce valuable knowledge (what you tried, why
it didn't work, what finally did) that immediately evaporates when the session ends.
A debug trail captures that reasoning incrementally so it's portable, shareable,
and useful for post-mortems.

---

## Output: DEBUG_TRAIL.md

Append-only. Never rewrite history — if a hypothesis was wrong, record that it was
wrong. The value is in the full chain of reasoning, not just the final answer.

```markdown
# Debug Trail: <short description of the bug>

**Started:** <timestamp>
**Status:** OPEN | RESOLVED | ABANDONED
**Symptom:** <exact error message or observed behavior>
**Affected:** <file/component/endpoint/user-facing feature>

---

## Entry 1 — <timestamp>

**Hypothesis:** <what you think might be causing this>
**Test:** <what you did to check it>
**Result:** <what actually happened>
**Conclusion:** <what this rules in or out>

---

## Entry N — <timestamp>
...

---

## Resolution (when RESOLVED)

**Root cause:** <the actual cause>
**Fix:** <what was changed and why>
**How to verify:** <how to confirm it's fixed>
**Why it happened:** <underlying reason — not just what broke, but why>
**Prevention:** <what would prevent this class of bug in future>

---

## Timeline
<git log or command history relevant to the fix, auto-generated>
```

---

## Workflow

### Starting a trail

When a debug session begins, create or open DEBUG_TRAIL.md in the project root
(or `.claude/DEBUG_TRAIL.md` to keep it out of the way).

Fill in:
- **Symptom** from the exact error message or reproduction steps the user gives
- **Affected** from what component/path the error points to

Start with Entry 1 immediately — even if the first hypothesis is wrong, record it.

### Appending entries during the session

After every meaningful action (a test run, a log read, a code change, a search),
append an entry. Don't batch them. The point is to capture the reasoning as it
happens, not reconstruct it afterward.

Keep entries short — 3-5 lines. The format is:
```
**Hypothesis:** ...
**Test:** ...
**Result:** ...
**Conclusion:** ...
```

If a test produced a surprising result, add a **Surprise:** line to call it out.
Surprises often point directly at the root cause.

### Closing the trail

When the bug is resolved, add a Resolution section. The **Why it happened** and
**Prevention** fields are the most important — they turn a one-off fix into
transferable knowledge.

Change Status to RESOLVED and record the timestamp.

If the session ends without resolution (time-boxed, deprioritized), set Status to
ABANDONED and add a **Parking lot** section with the most promising next steps.

### Background capture (hooks integration)

To capture the trail automatically in Claude Code, add a hook to `.claude/settings.json`
that appends a session summary after each tool use:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo '<!-- auto -->' >> .claude/DEBUG_TRAIL.md"
          }
        ]
      }
    ]
  }
}
```

The skill handles the structured entries — hooks handle the audit trail of raw
commands run.

---

## What makes a good debug trail

**Bad:** A list of things you tried, written retrospectively.

**Good:** A real-time log where each entry says *why* you thought that would work
and *what you learned* when it didn't. The trail should read like a conversation
between the engineer and the problem.

The Resolution section's **Why it happened** field is what separates a debug trail
from a bug report. Anyone can write "fixed null pointer in auth.py." A debug trail
explains why the null pointer was there in the first place.

---

## Multiple bugs in one session

If a session surfaces multiple bugs, keep one trail per bug. Name them:
`DEBUG_TRAIL_auth_null.md`, `DEBUG_TRAIL_cache_race.md`, etc.

A single trail with interleaved bugs is unreadable.
