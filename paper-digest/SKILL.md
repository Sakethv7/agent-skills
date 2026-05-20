---
name: paper-digest
description: >
  Digest an academic paper into a structured summary covering methodology, results,
  limitations, and follow-up questions. Use this skill whenever the user pastes an
  arXiv link, drops a PDF of a paper, or says "summarize this paper", "what does
  this paper claim", "explain this research", "break down this study", or wants to
  understand a scientific or technical paper quickly. Different from a generic
  summary: captures what was measured, what was held constant, and what the authors
  did not prove — the distinctions that matter when evaluating research.
---

# Paper Digest

## Output: DIGEST.md

One structured file covering:

```markdown
# <Title> (<Year>)

**Authors:** ...  **Venue:** ...  **Link:** ...

## One-line claim
The single sentence the paper is trying to prove.

## Problem and motivation
What gap or limitation in prior work does this address?

## Approach
What did they actually build or do? How is it different from baselines?

## Experimental setup
- Dataset(s) used
- Baselines compared against
- Metrics reported
- What was held constant (important: this constrains how far results generalize)

## Key results
| Claim | Evidence | Confidence |
|---|---|---|
| ... | Figure/Table N | Strong / Moderate / Weak |

## What the authors admit they didn't prove
Explicit limitations from the paper. If none stated, note that.

## What I'd probe further
3-5 questions the results don't answer, derived from reading the setup and results carefully.

## Related work to read
Papers this cites that seem load-bearing (not just polite citations).
```

---

## Workflow

### Step 1 — Get the paper

If given an arXiv URL, fetch the abstract page first to get the PDF link:
```
https://arxiv.org/abs/<id>  →  PDF at https://arxiv.org/pdf/<id>
```

If given a PDF directly, use `pdftotext` — almost all academic papers have text
layers. Do not OCR unless `pdftotext` returns garbage.

```bash
pdftotext <paper.pdf> /tmp/paper.txt
wc -c /tmp/paper.txt  # should be tens of thousands of bytes for a real paper
```

### Step 2 — Read the whole paper, not just the abstract

Abstracts are written to sell the paper. The methods, ablations, and limitations
sections are where the actual substance is. Pay specific attention to:

- Section 4-5 (experiments) — what they measured vs. what they assumed
- Appendix — often contains the ablation studies and failure cases
- Conclusion paragraph 2 — authors usually hedge here

### Step 3 — Distinguish claim from evidence

This is the core judgment the digest needs to make. For each major claim:
- Is it directly supported by a number in a table?
- Is it supported by a cherry-picked example (weaker)?
- Is it an interpretation the authors assert but don't measure?

Label confidence as Strong / Moderate / Weak accordingly.

### Step 4 — Write DIGEST.md

Use the template above. The "What I'd probe further" section should reflect genuine
reading of the experimental setup — what assumptions were made, what wasn't ablated,
what datasets were excluded. Don't just copy the authors' limitations section.

### Step 5 — Deliver

If `present_files` is available, use it. Otherwise report the path to DIGEST.md.

---

## What makes a good digest vs. a bad one

**Bad:** restates what the abstract says in different words.

**Good:** tells the reader what the paper actually proved vs. what it claimed, and
what questions remain open after reading it.

The "Key results" table with explicit confidence ratings and the "What the authors
didn't prove" section are what separate a digest from a summary.

---

## Known limitations

Multi-paper comparisons (literature reviews) are out of scope — this skill processes
one paper at a time. For batch processing, run the skill per paper and ask the user
to compare digests manually or prompt for a synthesis pass.
