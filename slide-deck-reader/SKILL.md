---
name: slide-deck-reader
description: >
  Convert a slide deck (PDF, PPTX, or image sequence) into a structured document
  that captures the argument being made — not just a list of bullets from each
  slide. Use this skill when the user wants to understand a presentation, extract
  the narrative from a deck, create speaker notes, turn slides into a readable
  document, or produce a summary of a recorded talk. The key distinction from a
  generic summary: slides are fragments that assume a speaker's context, so the
  skill reconstructs the implied argument, not just the visible text.
---

# Slide Deck Reader

## The core challenge

Slides are not documents. They're visual cues for a speaker. A bullet like
"Latency: 12ms → 4ms" means nothing without knowing: compared to what? Under what
load? Why does this matter? A naïve transcription of slide bullets produces output
that's just as incomplete as the original slide.

The job is to reconstruct the *argument* the deck was designed to support.

---

## Output: DECK_SUMMARY.md

```markdown
# <Deck Title> — <Author / Organization if visible> (<Date if visible>)

## What this deck is arguing
1-3 sentences: the central claim or recommendation the deck exists to make.

## Audience and context
Who is this deck for? What decision or action is it trying to drive?
(Infer from tone, jargon level, and slide structure if not stated explicitly.)

## Narrative structure
How does the deck build its argument? (e.g., "Problem → Root cause → Solution →
Evidence → Call to action" or "Current state → Future state → Gap → Plan")

## Slide-by-slide breakdown
### Slide N: <Title or inferred topic>
**Visible content:** [bullets, key numbers, diagram description]
**What this is doing narratively:** [setting context / making a claim / providing
evidence / transitioning / calling to action]
**Key insight (if any):** [the one thing this slide is trying to land]

## Key claims and supporting evidence
| Claim | Evidence on slides | Confidence |
|---|---|---|
| ... | Slide N, chart/number | Strong / Asserted / Unclear |

## Numbers and data points
All quantitative claims in one place: metric, value, slide reference.

## Action items or recommendations
If the deck ends with a recommendation or asks for something, state it clearly.

## What's missing
Gaps in the argument — claims made without evidence, assumptions not stated,
questions the deck raises but doesn't answer.
```

---

## Workflow

### Step 1 — Get the content

**PDF slide deck:**
```bash
pdftotext <deck.pdf> /tmp/slides_text.txt
wc -l /tmp/slides_text.txt
```

If `pdftotext` yields real text, use it. Many PDF decks have text layers.

If the deck is image-only (exported from Keynote/PowerPoint as images), rasterize:
```bash
pdftoppm -jpeg -r 150 <deck.pdf> /tmp/slides
```
Then read each slide image directly with the vision model — don't run tesseract on
slides (too much visual structure, non-horizontal text, diagrams).

**PPTX files:**
```bash
python3 -c "
from pptx import Presentation
import sys
prs = Presentation(sys.argv[1])
for i, slide in enumerate(prs.slides, 1):
    print(f'--- Slide {i} ---')
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                print(para.text)
" <deck.pptx>
```

Install if needed: `pip install python-pptx`

### Step 2 — Identify slide types

Before writing, categorize each slide:
- **Title / section break** — navigation, no content to extract
- **Claim slide** — makes an assertion (often a headline + supporting bullets)
- **Evidence slide** — chart, table, or data supporting a prior claim
- **Diagram slide** — architecture, flow, or process (describe it)
- **Call to action** — what the deck is asking for

This categorization shapes how you write the slide-by-slide breakdown.

### Step 3 — Infer the argument structure

Read all slides before writing anything. Ask:
- What problem does slide 1-3 establish?
- What solution or recommendation does the deck build toward?
- Which slides are load-bearing (make a key claim) vs. filler?
- Does the evidence actually support the claims?

Write the "Narrative structure" section first — it forces you to have a thesis
before summarizing individual slides.

### Step 4 — Extract numbers faithfully

Never paraphrase numbers. Copy them exactly and note the slide they appear on.
If a chart has no axis labels or units, flag it in "What's missing."

### Step 5 — Flag gaps and weak evidence

Common patterns to flag:
- Claim slide with no corresponding evidence slide
- Y-axis that doesn't start at zero (visually inflates differences)
- "3x improvement" with no baseline stated
- Competitor comparison with no methodology
- Projection charts with no confidence interval

### Step 6 — Deliver

If `present_files` is available, use it. Otherwise report the path to DECK_SUMMARY.md.

---

## What makes a good deck summary vs. a bad one

**Bad:** A list of every bullet from every slide. This is just the deck again,
slightly reformatted.

**Good:** A document that someone who hasn't seen the deck could read and understand
the argument — including where the argument is strong, where it's thin, and what it's
asking for.

The "What's missing" section is often the most valuable part.

---

## Known limitations

- Animations and builds: exported PDFs show the final state of each slide only;
  intermediate states are lost
- Speaker notes: accessible from PPTX via `python-pptx` but not from PDF exports
- Video embeds: not extractable from any format
- Highly visual decks (mostly images, minimal text): summarize what's visible and
  note that the deck relies heavily on visuals
