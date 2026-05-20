---
name: receipt-scanner
description: >
  Extract structured expense data from one or more scanned receipts or invoice
  images and produce a CSV ready for expense reporting or accounting import. Use
  this skill when the user has photos or scans of receipts, invoices, or expense
  documents and wants to extract merchant, date, amount, category, or build an
  expense report. Works on individual receipts or a folder of images. Output is
  always a CSV plus a brief exceptions report listing anything that couldn't be
  read with confidence.
---

# Receipt Scanner

## Outputs

- **expenses.csv** — one row per receipt, machine-readable
- **exceptions.txt** — receipts where extraction was uncertain, with the raw OCR

---

## CSV Schema

```
date,merchant,amount,currency,category,payment_method,tax,tip,total,notes,source_file
2024-03-15,Whole Foods,42.18,USD,Groceries,Visa,3.21,,45.39,,receipt_001.jpg
```

| Column | Notes |
|---|---|
| `date` | ISO 8601 (YYYY-MM-DD). If only month/year readable, use first of month. |
| `merchant` | Clean name, not address. "Starbucks" not "STARBUCKS #12345 S MAIN ST" |
| `amount` | Subtotal before tax and tip, if separable. Otherwise total. |
| `currency` | ISO 4217 (USD, EUR, GBP, etc.). Default USD if not shown. |
| `category` | Inferred from merchant (see category map below). |
| `payment_method` | Last 4 digits if shown, or card type. Empty if not readable. |
| `tax` | Tax amount if shown separately. |
| `tip` | Tip amount if shown separately. |
| `total` | Total charged (most authoritative figure on the receipt). |
| `notes` | Anything notable — "gratuity included", "itemized", "partial read". |
| `source_file` | Filename of the source image. |

### Category map (infer from merchant name/type)

| Merchant type | Category |
|---|---|
| Restaurant, café, bar, food delivery | Meals & Entertainment |
| Grocery, supermarket | Groceries |
| Gas station, fuel | Transportation |
| Ride share, taxi, transit | Transportation |
| Hotel, lodging, Airbnb | Lodging |
| Airline, train, bus ticket | Travel |
| Office supply, printer, software | Office Supplies |
| Medical, pharmacy | Healthcare |
| Retail, general merchandise | General |
| Unknown | Uncategorized |

---

## Workflow

### Step 1 — Collect inputs

If given a single image: process it directly.
If given a folder path: list all `.jpg`, `.jpeg`, `.png`, `.pdf` files and process
each one.

```bash
ls -1 <folder>/*.{jpg,jpeg,png,pdf} 2>/dev/null
```

### Step 2 — OCR each receipt

For image files:
```bash
tesseract <receipt.jpg> /tmp/receipt_<N>_text --psm 6
```

For PDF receipts (e.g., email-generated invoices):
```bash
pdftotext <receipt.pdf> /tmp/receipt_<N>_text.txt
```

Use `--psm 6` (assume uniform block of text) for receipts — they're not paragraph
prose, so the default page segmentation mode often fragments numbers.

### Step 3 — Parse each OCR output

Read the raw text and extract:

1. **Date** — look for date patterns near the top of the receipt. Formats vary
   widely: `03/15/24`, `Mar 15 2024`, `15-03-2024`. Normalize to YYYY-MM-DD.

2. **Merchant** — usually the largest text at the top, or the first non-date line.
   Strip address, phone number, and store ID suffixes.

3. **Total** — look for labels: `TOTAL`, `AMOUNT DUE`, `CHARGE`, `GRAND TOTAL`.
   Take the largest clearly-labeled amount if multiple are present.

4. **Tax and tip** — look for `TAX`, `GST`, `HST`, `VAT`, `GRATUITY`, `TIP` lines.

5. **Payment method** — look for card type + last 4 digits near the bottom.

When a field is ambiguous or unreadable, leave it empty and add the receipt to
exceptions.txt — never guess a dollar amount.

### Step 4 — Validate amounts

Before writing the CSV, sanity-check: `amount + tax + tip ≈ total`. If the numbers
don't add up (within $0.05), flag it in exceptions.txt with the raw OCR.

### Step 5 — Write outputs

Append each successfully parsed receipt to expenses.csv. Log failures and low-confidence
extractions to exceptions.txt:

```
--- receipt_007.jpg ---
REASON: Could not identify total — multiple unlabeled amounts
RAW OCR:
<paste raw tesseract output>
```

### Step 6 — Deliver

Report how many receipts were processed, how many succeeded, how many went to
exceptions. If `present_files` is available, deliver both files.

---

## Known hard cases

| Situation | Behavior |
|---|---|
| Crumpled or low-contrast receipt | OCR quality degrades — flag in exceptions |
| Non-English receipt | Add `-l <lang>` to tesseract; category inference may fail |
| Handwritten receipt | tesseract cannot handle it; flag immediately |
| Digital invoice PDF | Usually has text layer; use pdftotext, skip OCR |
| Receipt shows only partial total (tip line blank) | Use subtotal + tax as total estimate; note in `notes` column |
| Multiple receipts in one image | Split into separate images before processing; flag if unsplittable |

---

## What this skill does not do

- Submit to accounting systems (QuickBooks, Expensify, etc.) — it produces a CSV
  you import yourself
- Verify that amounts match a bank statement
- Handle multi-page itemized invoices (only the summary line items)
