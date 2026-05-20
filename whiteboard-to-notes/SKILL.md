---
name: whiteboard-to-notes
description: >
  Convert a photo of a whiteboard, sticky-note wall, or handwritten notes into
  clean, structured markdown. Use this skill whenever the user uploads a photo of
  a whiteboard, a physical brainstorm session, handwritten meeting notes, a
  mind map drawn on paper, or any image where the primary content is handwritten
  or hand-drawn text. Do NOT use tesseract — whiteboard photos need vision model
  reading, not OCR. Output is always structured markdown that preserves the
  spatial and logical relationships visible in the image.
---

# Whiteboard to Notes

## Critical: use vision, not tesseract

Tesseract is trained on printed text. It fails on:
- Handwriting of any quality
- Diagrams, arrows, boxes
- Non-horizontal text
- Mixed text and drawings

For whiteboard photos, read the image directly using the vision model. Pass the
image as a base64-encoded input or file attachment and ask the model to transcribe
and structure what it sees.

---

## Output: NOTES.md

```markdown
# <Inferred title or "Untitled Session"> — <date if visible>

## Summary
1-2 sentence description of what this whiteboard session covered.

## Main Topics
<Preserve the high-level structure visible on the whiteboard — sections, clusters,
headers>

### <Topic 1>
- <Item>
- <Item>
  - <Sub-item if indented or connected by arrow>

### <Topic 2>
...

## Diagrams and Flows
Describe any flowcharts, architecture diagrams, or relationship maps. Use ASCII
or Mermaid if the structure is clear enough to reconstruct.

## Action Items
If any TO-DO, ACTION, or circled items are visible, list them here.

## Unclear or Illegible
List anything that couldn't be confidently read, with a best guess if possible.
```

---

## Workflow

### Step 1 — Assess image quality

Before transcribing, look at:
- Is the whiteboard in focus and well-lit?
- Is there glare obscuring sections?
- Is the text large enough to read?

If quality is poor, tell the user: "Parts of this are hard to read — I'll do my
best and flag uncertain sections."

### Step 2 — Read spatially

Whiteboards are not linear documents. Content is organized in 2D space. Before
writing markdown:

- Identify the main regions (top-left block, right column, center diagram, etc.)
- Understand which items are clustered together
- Follow arrows — they encode relationships and flow
- Identify headers vs. body text (usually larger, underlined, or circled)

### Step 3 — Transcribe and structure

Map the 2D layout to hierarchical markdown. Guiding principles:

- Spatial proximity → nesting (items near each other are sub-items of their header)
- Arrows → relationships (document as "A → B" or in a Mermaid diagram)
- Boxes → grouping (items inside a box belong to the same concept)
- Circles or stars → emphasis (flag as "Key point:" or action item)

When two items are connected by an arrow, either use a list with indentation or
a Mermaid flowchart:

```
graph LR
  A[User Request] --> B[Auth Check]
  B --> C{Authorized?}
  C -->|yes| D[Process]
  C -->|no| E[Reject]
```

### Step 4 — Handle multiple images

If the user provides multiple photos of the same session (e.g., different sections
of a large whiteboard), process them in order and combine into a single NOTES.md.
Note where one photo ends and the next begins only if there's a clear break in
content.

### Step 5 — Flag uncertainty

For each section you're not confident about, add a callout:

```markdown
> **Unclear:** This section looks like "deploy pipeline" but the last word may be
> "plugin" — low confidence.
```

Don't silently guess. The user can clarify.

### Step 6 — Deliver

If `present_files` is available, use it. Otherwise report the path to NOTES.md.

---

## What makes a good transcription

**Bad:** A flat bullet list of every word you can read, in reading order.

**Good:** A structured document that preserves the *relationships* visible on the
whiteboard — what's a heading vs. a detail, what flows into what, what was
circled for emphasis.

The markdown should make sense to someone who wasn't in the room, not just to
someone who already knows what the whiteboard says.

---

## Known limitations

- Dense handwriting in small font may be partially unreadable even with vision
- Diagrams with very thin lines or light marker may not render clearly
- Multi-color whiteboards: color coding is noted in text ("in red: ...") but the
  markdown itself is monochrome
- Photos taken at sharp angles introduce distortion — spatial relationships may be
  harder to infer
