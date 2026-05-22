---
name: data-profiler
description: >
  Profile any document or data file — CSV, Excel, Parquet, JSON, Word, PowerPoint,
  PDF — and produce a structured insights report: what the data means, patterns,
  anomalies, what's missing, and what to do next. Use this skill when the user
  drops a file and wants to understand it, asks "what's in this file", "profile
  this data", "what does this spreadsheet mean", "analyze this", "give me insights
  on this deck/report/dataset", or when a file appears in context and the user
  wants to understand it before working with it. Goes beyond statistics — always
  explain what the numbers mean and why they matter.
---

# Data Profiler

## Output: INSIGHTS.md

Not just statistics — interpretation. The report should answer: "What is this
file telling me, and what should I do about it?"

```markdown
# Insights: <filename>

**File type:** ...  **Size:** ...  **Profiled:** <date>

## What this file is
1-2 sentences: what kind of data this is, who likely created it, what it represents.

## Structure
| Property | Value |
|---|---|
| Rows / records | ... |
| Columns / fields | ... |
| Date range (if applicable) | ... |
| Key identifiers | ... |

## Field-by-field breakdown
For each column / section / slide:
- What it represents
- Data type and range
- Notable values (max, min, mode, common values)
- Quality issues (nulls, inconsistencies, outliers)

## Patterns and signals
What trends, clusters, or relationships are visible in the data?
What is the data showing — not just what it contains.

## Anomalies and quality issues
| Issue | Location | Severity | Recommended action |
|---|---|---|---|
| ... | ... | High/Med/Low | ... |

## What's missing
Fields, time periods, or context that would make this data more useful or
interpretable, but aren't present.

## What to add / improve
Concrete suggestions — new columns, better formatting, additional context,
validation rules.

## What this means / so what
The 3-5 most important takeaways. If someone asked "what does this file tell you?",
this is the answer.

## Suggested next steps
What analysis or action would be most valuable given what's in this file?
```

---

## Workflow by file type

### CSV / Parquet / JSON (tabular data)

```python
import pandas as pd

# Load
if path.endswith(".csv"):
    df = pd.read_csv(path)
elif path.endswith(".parquet"):
    df = pd.read_parquet(path)
elif path.endswith(".json"):
    df = pd.read_json(path)

# Structure
print(df.shape)
print(df.dtypes)
print(df.describe(include="all"))
print(df.isnull().sum())
print(df.nunique())

# Outliers (numeric cols)
for col in df.select_dtypes("number"):
    q1, q3 = df[col].quantile([0.25, 0.75])
    iqr = q3 - q1
    outliers = df[(df[col] < q1 - 1.5*iqr) | (df[col] > q3 + 1.5*iqr)]
    if len(outliers):
        print(f"{col}: {len(outliers)} outliers")

# Duplicates
print(f"Duplicate rows: {df.duplicated().sum()}")
```

Go beyond the numbers: interpret what the columns represent, what the distributions
suggest, and what the anomalies might mean for downstream use.

### Excel (.xlsx / .xls)

```python
import pandas as pd
xl = pd.ExcelFile(path)
print(xl.sheet_names)

for sheet in xl.sheet_names:
    df = xl.parse(sheet)
    # profile each sheet as tabular data above
```

Also look for:
- Merged cells (indicate manual formatting, may break parsing)
- Formulas (cells that compute rather than store values)
- Multiple header rows
- Hidden sheets
- Pivot tables or charts embedded in sheets

Explain what each sheet represents and how the sheets relate to each other.

### PowerPoint (.pptx)

```python
from pptx import Presentation
prs = Presentation(path)
for i, slide in enumerate(prs.slides, 1):
    print(f"--- Slide {i} ---")
    for shape in slide.shapes:
        if shape.has_text_frame:
            print(shape.text_frame.text[:200])
```

Profile:
- Total slides, slide types (title, content, chart, image)
- Narrative structure: what argument does the deck make?
- Data claims: any numbers stated? Are they sourced?
- Visual content: charts, images, diagrams — described
- What's missing: slides that seem to assume context not in the deck

### Word (.docx)

```python
from docx import Document
doc = Document(path)
for para in doc.paragraphs:
    print(para.style.name, ":", para.text[:100])
```

Profile:
- Document type (report, memo, contract, template, etc.)
- Section structure and hierarchy
- Key claims, dates, names, numbers
- Tables (parse and describe)
- What's missing or incomplete

### PDF

Use `pdftotext` fast-path or fall back to OCR (see scanned-doc-reader skill).
Then profile the extracted text as a document.

---

## The interpretation layer (always required)

Statistics alone are not insights. After extracting the numbers, always answer:

1. **What is this?** — What does this file represent in the real world?
2. **What's notable?** — What would surprise someone who knows this domain?
3. **What's wrong?** — Data quality issues, inconsistencies, suspicious values.
4. **What's missing?** — What context would make this more useful?
5. **So what?** — If someone acted on this data, what would they do?

The "What to add / improve" section should be concrete. Not "add more data" but
"add a currency column — amounts appear to be mixed USD and EUR based on the
merchant names, which will cause incorrect aggregations."

---

## Install dependencies

```bash
pip install pandas openpyxl python-pptx python-docx pyarrow
```

For PDF: `brew install poppler tesseract` (macOS) or `apt-get install poppler-utils tesseract-ocr`
