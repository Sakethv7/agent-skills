---
name: contract-extractor
description: >
  Extract structured information from a legal contract or agreement: parties, key
  dates, obligations, rights, penalties, and ambiguous or risky clauses. Use this
  skill whenever the user uploads a PDF or pastes text of a contract, NDA, lease,
  service agreement, employment contract, or any legal document and wants to
  understand what it says — especially what they're agreeing to, what deadlines
  exist, and what could go wrong. Always flag uncertainty; never assert legal
  conclusions with false confidence.
---

# Contract Extractor

**Important:** This skill extracts and organizes information — it does not provide
legal advice. Always tell the user: "This is an extraction, not legal advice. Have
a lawyer review before signing anything significant."

---

## Output: CONTRACT_SUMMARY.md

```markdown
# Contract Summary: <Document Title or Type>

**Extracted on:** <date>
**Document type:** NDA / Service Agreement / Employment / Lease / Other
**Pages:** N

---

## Parties
| Role | Name / Entity | Jurisdiction (if stated) |
|---|---|---|
| Party A | ... | ... |
| Party B | ... | ... |

---

## Key Dates and Deadlines
| Event | Date | Hard deadline? |
|---|---|---|
| Effective date | ... | — |
| Expiration / termination | ... | Yes/No |
| Notice period required to terminate | ... | Yes/No |
| Payment due dates | ... | Yes/No |

---

## Core Obligations
### Party A must:
- ...

### Party B must:
- ...

---

## Rights Granted
- ...

---

## Restrictions and Prohibitions
- ...

---

## Financial Terms
| Item | Amount | Timing | Conditions |
|---|---|---|---|
| ... | ... | ... | ... |

---

## Termination Conditions
How can each party exit, and what are the consequences?

---

## Penalties and Remedies
What happens if a party breaches? Are there liquidated damages, indemnification
clauses, or limitation of liability caps?

---

## Governing Law and Dispute Resolution
Jurisdiction, arbitration clauses, class action waivers.

---

## Flagged Clauses — Review These
List clauses that are:
- Ambiguous (could be interpreted multiple ways)
- Unusually broad (e.g., IP assignment covering work done outside the engagement)
- Asymmetric (one party has a right the other doesn't)
- Missing (standard clauses that aren't present, e.g., no limitation of liability)

For each: quote the relevant text verbatim, then explain the concern.

---

## What's Not Covered Here
Anything the skill couldn't extract with confidence — note it explicitly rather than
guessing.
```

---

## Workflow

### Step 1 — Get the text

Most contracts are PDFs with text layers:

```bash
pdftotext <contract.pdf> /tmp/contract.txt
wc -l /tmp/contract.txt
```

If garbled (scanned contract), fall back to OCR:
```bash
pdftoppm -jpeg -r 200 <contract.pdf> /tmp/contract_pages
for img in /tmp/contract_pages-*.jpg; do
    tesseract "$img" stdout 2>/dev/null >> /tmp/contract_ocr.txt
done
```

### Step 2 — Identify document type and parties

Read the first page and recitals section. Note the document type — it determines
which sections to prioritize (NDAs → confidentiality scope; employment → IP
assignment, non-compete; leases → maintenance obligations, renewal options).

### Step 3 — Extract, don't interpret

Fill in the summary template by quoting or closely paraphrasing the contract text.
Where a clause is ambiguous, quote it verbatim under "Flagged Clauses" and explain
both interpretations.

Do not:
- Conclude that a clause is "standard" without reading it (standards vary by
  jurisdiction and industry)
- Omit a clause because it seems boilerplate
- Paraphrase in a way that resolves ambiguity the contract left open

### Step 4 — Flag asymmetries and missing protections

Common things worth flagging:
- IP assignment clauses that sweep in work done outside the engagement scope
- Non-compete clauses with broad geography or long duration
- Unilateral amendment rights (one party can change terms without consent)
- Indemnification that doesn't have a liability cap
- Auto-renewal with short cancellation windows
- Absence of a limitation of liability clause
- Force majeure that's one-sided or absent

### Step 5 — Deliver

If `present_files` is available, use it. Otherwise report the path.

Always close with: "This is a structural extraction. Have a qualified attorney review
before signing, especially the flagged clauses."

---

## What this skill does not do

- Assess whether the contract terms are fair or market-standard
- Predict how a clause would be interpreted by a court
- Compare against other versions of the contract
- Identify fraud or misrepresentation
