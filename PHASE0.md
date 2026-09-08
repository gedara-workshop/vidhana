# Phase 0 — Feasibility

Reading 15–20 real gazettes by hand before writing any scraper or extraction code.
Goal: replace guesses about the data with facts, and hand-write 5 summaries as an
evaluation set for the LLM structuring step.

**Status: COMPLETE.** 21 gazettes acquired, machine-surveyed and read in full.
Open questions closed (§7). Five reference summaries written (§6) — with a known
limitation recorded there. Phase 0 findings are ready to inform Phase 1.

---

## 1. The source

**Listing page:** https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602

Reachable from the IRD site as *Home :: Downloads :: Gazette*. Note the lowercase
`gazette.aspx` — the capitalised `Gazettes.aspx` guess is a 404.

**Structure.** SharePoint page, one flat HTML document. Per year there is an
`<h4>` heading followed by a 3-column table:

| Gazette Date | Gazette No | Gazette Description |
|---|---|---|

The description cell holds the `<a href>` to the PDF. Years other than the newest
carry `style="display:none"` and are expanded client-side by a fold widget.

**Findings that matter for the scraper:**

- **No pagination.** All 20 years are in the single HTML response. One GET gets
  the entire corpus — no page walking, no `__doPostBack`, no JS execution needed.
- **137 gazettes total, 2006–2026** (138 table rows, one of which is empty). Per year: 2026:2, 2025:4, 2024:3, 2023:3,
  2022:9, 2021:6, 2020:1, 2019:7, 2018:23, 2017:5, 2016:8, 2015:3, 2014:8,
  2013:4, 2012:7, 2011:8, 2009:8, 2008:10, 2007:15, 2006:4.
  **2010 is absent entirely** — no heading, not an empty one.
- **Volume is low.** ~3–6 new gazettes/year recently. A daily poll of one page is
  ample; this does not need to be clever.
- **No `robots.txt`** (returns 404), so nothing is disallowed. Still be polite —
  single host, government infrastructure. Current fetcher sleeps 1.5s.
- **All links are English-only** (`_E`). Sinhala/Tamil editions of the same
  gazettes are not linked from this page.
- One **empty `<tr>`** under 2006 with no number, date or URL. Must be skipped or
  it becomes a null row.

**Filename patterns are inconsistent** — three variants, all meaning the same thing:

```
2026_2500_106_E.pdf      underscore separator
2026_2481-22_E.pdf       hyphen separator
2014_1868_10_(E).pdf     parenthesised language tag
2013_1823_05 (E).pdf     ← raw literal space in the href, needs URL-encoding
TP_2021_ 2217-07_E.pdf   ← "TP_" prefix AND a stray space mid-filename
```

Do not parse identity out of the filename. Use the listing's `Gazette No` column.
`urllib`/`requests` will not encode those spaces for you — quote the path.

---

## 2. The sample

21 PDFs in `data/gazettes/` (gitignored), recorded in `data/manifest.csv` with
`source_url` and `sha256`. Weighted toward recent (v0 scope) with older years
sampled to see how far back the format holds.

Re-fetch with `python3 scripts/phase0_fetch.py --sample`.

---

## 3. Machine survey — what the PDFs actually are

### Scan quality: better than the README assumed — with one real exception

**No document is a scan. All 21 are native-text PDFs, back to 2007.** Text
density is 1,700–3,700 chars/page across the whole range. Producers run from
`Acrobat Distiller 3.01` (2007) to `Adobe PDF Library 17.0` (2026) — always a
digital typesetting pipeline, never a scanner.

**But native-text does not mean fully extractable.** `2414/14` (Dec 2024,
withholding tax on outward remittances) embeds **three rasterised form pages**
— pages 5, 6 and 7 carry images of roughly 2600×3100 px at ~410 ppi, and those
pages yield only 600 / 330 / 228 characters of text, all of it running header
and section title. The document's own item 9 reads:

```
9.  Format of the Tax Clearance Application
    <running header>
    <nothing>
```

The form a reader actually needs is inside the image. `pdftotext` returns
nothing for it, silently.

> **Consequence:** OCR is **not** needed for whole documents, but it **is**
> needed selectively for embedded form/schedule images. The trigger is not "is
> this a scan" — it is "does this page carry a large image and almost no text".
> 1 of 21 documents (~5%) hits this, and it is a substantive one.
>
> Detection rule that works on this sample: flag any page where
> `pdfimages -list` reports an image wider than ~1000px **and** the page yields
> under ~400 characters. On this corpus that flags exactly `2414/14` pp. 5–7 and
> nothing else. A sparse page alone is not enough — `2217/07` p.21 has only 233
> characters but is a genuine near-empty table, not an image.

### Language: the real problem is encoding, not multilingual content

Every gazette is a bilingual document — a Sinhala half and an English half — but
the English body text is clean and complete in all 21. The trap is *how* the
Sinhala is encoded, and there are two eras:

**Legacy font (20 of 21 documents, 2007 → 2025).** Sinhala is stored in a
non-Unicode legacy font. `pdftotext` emits it as **plausible-looking ASCII**:

```
Y%S ,xld m%cd;dka;%sl iudcjd§ ckrcfha .eiÜ m;%h     ← this is Sinhala
w;s úfYI                                             ← "Extraordinary"
```

This is the nastiest finding in the sample. It is not detectable by a charset or
`isascii()` check, and it will look like English to a naive language filter and to
an LLM. Documents measure 95–97% ASCII, but a slice of that ASCII is fake.

**Unicode (1 of 21, only the newest — 2481/22, Mar 2026).** Real Unicode Sinhala:

```
ශ්‍රී ලංංකාා ප්‍රජාාතාාන්ත්‍රික සමාාජවාාදී ජනරජයේ� ගැැසට් පත්‍රය
```

Note the doubled vowel signs (`ලංංකාා` for `ලංකා`) and a `�` — even the modern
Unicode extraction is lossy. Do not trust extracted Sinhala for display.

**No Tamil in any sampled document.**

> **Consequence:** strip the Sinhala rather than translate it. Filtering must be
> positional/structural (the English half is a known region of the document), not
> charset-based. See the boilerplate list below — it removes most of it.

### Boilerplate appearing in all 21

Constant across 20 years, safe to strip before sending text to an LLM:

```
The Gazette of the Democratic Socialist Republic of Sri Lanka
EXTRAORDINARY
(Published by Authority)
PART I : SECTION (I) — GENERAL
Government Notifications
PRINTED AT THE DEPARTMENT OF GOVERNMENT PRINTING, SRI LANKA.
This Gazette Extraordinary can be downloaded from www.documents.gov.lk
Y%S ,xld m%cd;dka;%sl iudcjd§ ckrcfha .eiÜ m;%h      (legacy Sinhala, 19/21)
w;s úfYI                                              (legacy Sinhala, 19/21)
```

Plus a **per-page running header** on every page after the first, which is the
legacy-Sinhala and English title on one line, prefixed with the page number:

```
2A     I fldgi ( ^I& fPoh - YS% ,xld m%cd;dka;s%l iudcjd§ ckrcfha w;s úfYI .eiÜ m;%h - 2024'12'11
       Part I : Sec. (I) - GAZETTE EXTRAORDINARY OF THE DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA - 11.12.2024
```

…and a print-run footer like `1A - G 43237 - 05 (12/2024)`.

### Extraction: use `pdftotext -layout`

Not cosmetic — a correctness issue. Without `-layout`, clause numbers detach from
their text and land on their own lines, which destroys the numbering of a legal
instrument:

```
plain:              -layout:
  1.2                 1.1  Every invoice issued pursuant to this specification
                           shall be prominently titled "TAX INVOICE''.
  Every invoice…      1.2  The title shall appear in a conspicuous place…
```

`-layout` keeps `1.1`, `(i)`, `(iii)`, `a.` bound to their clauses. It also
introduces leading indentation and literal tabs — normalise whitespace after
extraction, not before.

### Header parsing

The English header line is the reliable anchor across all 20 years:

```
No. 2481/22 - FRIDAY, MARCH 27, 2026
```

A naive `^No\. (\S+) - (.+, \d{4})$` matches only **19/21**. The variance:

- Casing is arbitrary: `FRIDAY, MARCH 27, 2026`, `thursday, march 27, 2025`,
  `Wednesday, December 11, 2024` — all appear.
- Stray space inside the number: `No. 2456 /02`
- Missing comma before the year: `No. 2064/54 - SUNDAY, APRIL 01 2018`
- Leading indentation from `-layout`.

This tolerant form matches **21/21**:

```python
re.compile(r'^[ \t]*No\.\s*([0-9]+\s*[/$]\s*[0-9]+)\s*[-–—]\s*(.+?,?\s*\d{4})[ \t]*$',
           re.M | re.I)
```

### ⚠ The PDF header number is not always the listing number

Zero-padding disagrees between the two sources:

| Listing | PDF header |
|---|---|
| `2217/07` | `2217/7` |
| `1487/03` | `1487/3` |

Also `wxl 2295$10` in the Sinhala line — `$` where the English uses `/`, an
artifact of the legacy font mapping.

> **Consequence:** the **listing page is the identity source of truth**, not the
> PDF. Normalise to the listing's zero-padded `NNNN/NN`. If the scraper ever keys
> on the PDF header, `2217/7` and `2217/07` become two records for one gazette.

### ⚠ Supersession is the norm, not an edge case

**16 of 21 documents contain amendment or rescission language; 8 explicitly
cross-reference other gazettes by number.** A gazette is rarely a standalone
statement — it is usually a diff against an earlier one.

The clearest example is sitting in the sample, and it is three documents long:

| Gazette | Date | What it does | Effective |
|---|---|---|---|
| `2463/05` | 17 Nov 2025 | Specifies the VAT Tax Invoice format | 01 Jan 2026 |
| `2481/22` | 27 Mar 2026 | New format; makes `2463/05` optional, **rescinds** it | 01 Jul 2026 |
| `2500/106` | 06 Aug 2026 | Amends `2481/22`: effective date **"July 01, 2026" → "October 01, 2026"** | 01 Oct 2026 |

> **This is the product thesis in miniature.** The README's headline example says
> `2481/22` mandates the new invoice format "starting July 1, 2026". As of
> `2500/106`, that is **wrong** — it was postponed to October 1, 2026. The README
> needs updating, and more importantly: a system that ingests gazettes as
> independent documents will confidently tell users the wrong date. Showing
> `2463/05` or an unamended `2481/22` as live guidance is worse than showing
> nothing.
>
> **Consequences for the schema:** a gazette needs `amends` / `rescinded_by`
> edges, and `effective_date` must be a *derived, resolvable* field separate from
> publication date — not a value scraped once and frozen.

**Cross-reference numbers are inconsistently zero-padded**, and inconsistently so
even within the same convention:

```
No. 2104/4    (listing: 2104/04)      No. 2295/08   (padded)
No. 1986/9    (listing: 1986/09)      No. 2217/7    (unpadded)
```

Reference resolution must normalise to the listing's padded form or the edges
will silently fail to connect.

### Content shape

Documents are short — 1–7 pages typically, one outlier at 43 (`2217/07`). The body
is a consistent legal skeleton: enabling Act → operative order → signature block
(Commissioner General's name, department, place, date) → optional Schedule or
Annexure carrying the substance. The signature block is a clean, consistently
positioned source for the `authority` field.

Original-document typos exist and should be preserved, not silently corrected —
e.g. 2481/22 Annexure reads "top right-hand **comer**".

---

## 4. Reading checklist

Mark these off as you read. Add per-gazette notes in section 5.

| Read | Gazette No | Date | Pages | Description |
|:--:|---|---|---|---|
| [ ] | `2500/106` | 06 Aug 2026 | 1p | The format and specification of the Tax Invoice to be issued by ev… |
| [ ] | `2481/22` | 27 Mar 2026 | 4p | The format and specification of the Tax Invoice to be issued by ev… |
| [ ] | `2463/05` | 17 Nov 2025 | 4p | The format and specification of the Tax Invoice to be issued by ev… |
| [ ] | `2456/02` | 29 Sep 2025 | 4p | Value Added Tax Act, No. 14 of 2002 - Conditions and specification… |
| [ ] | `2443/30` | 01 Jul 2025 | 4p | Value Added Tax Act, No. 14 of 2002, Procedure for Collecting and … |
| [ ] | `2429/39` | 27 Mar 2025 | 1p | Stamp Duty (Special Provisions) Act, No. 12 Of 2006, Order under S… |
| [ ] | `2414/14` | 11 Dec 2024 | 7p | Inland Revenue Act, No. 24 of 2017, Regulations under Section 86 (… |
| [ ] | `2378/33` | 04 Apr 2024 | 1p | Inland Revenue Act, No. 24 of 2017, Notice under Subsection (3) of… |
| [ ] | `2376/25` | 21 Mar 2024 | 5p | Inland Revenue Act, no. 24 of 2017, Regulation under Section 123 (… |
| [ ] | `2363/22` | 19 Dec 2023 | 1p | Order under Section 2A of Value Added Tax Act, No. 14 of 2002 as a… |
| [ ] | `2334/21` | 31 May 2023 | 2p | Notice made Under Section 102 of Inland Revenue Act, No. 24 of 201… |
| [ ] | `2316/13` | 24 Jan 2023 | 4p | Order to specify matters relation to and the manner in which tax i… |
| [ ] | `2312/73` | 31 Dec 2022 | 1p | Stamp Duty (Special Provisions) Act, No. 12 of 2006, Order under S… |
| [ ] | `2295/10` | 31 Aug 2022 | 10p | Regulations made under Section 4 of the Casino Business (Regulatio… |
| [ ] | `2217/07` | 02 Mar 2021 | 43p | Regulations on Transfer Pricing |
| [ ] | `2149/18` | 14 Nov 2019 | 1p | Stamp Duty (Special Provisions) Act No. 12 of 2006 - Order under S… |
| [ ] | `2064/54` | 01 Apr 2018 | 1p | Notification specify the taxes or other levies which the deduction… |
| [ ] | `1991/35` | 02 Nov 2016 | 3p | The Facilitation of the Implementation of Revenue Administration M… |
| [ ] | `1868/10` | 23 Jun 2014 | 4p | Order to specify matters relating to and the manner in which Tax i… |
| [ ] | `1728/13` | 19 Oct 2011 | 1p | Amendment to the Gaz. Ex. No. 1704/18 of 06.05.2011 - Inland Reven… |
| [ ] | `1487/03` | 05 Mar 2007 | 2p | The Inland Revenue Act - The Approval of Authorized Representative… |
---

## 5. Per-gazette notes

Free-form as you read. Anything that surprises you, anything a scraper or an LLM
would get wrong, anything the machine survey above missed or got wrong.

<!-- template:
### 2481/22 — 27 Mar 2026
- What it does:
- Surprises / quirks:
- Would the machine survey have handled it:
-->

---

## 6. Reference summaries (evaluation set)

> ⚠ **Known limitation — read before trusting any score against this set.**
>
> These five were written by Claude. Dinal decided not to author or correct them,
> so **this is a reference set, not an independent evaluation set.**
>
> Grading Claude's extraction against Claude's summaries measures *self-
> consistency*, not accuracy. Both sides share the same reading of the same
> documents and therefore the same blind spots: if the read misidentified an
> effective date or an audience, the summary and the extraction will agree on
> the error and the score will look clean.
>
> **What this set can legitimately do:** catch regressions (a change that breaks
> something previously working), and catch omissions against a fixed checklist.
> **What it cannot do:** establish that the pipeline is correct, or justify a
> claim of accuracy to anyone. Do not quote a number derived from it as an
> accuracy figure.
>
> The weakness is cheap to fix later — correcting these by hand, at any point,
> converts the set from self-consistent to independent. Until that happens,
> treat green results here as "nothing broke", never as "it works".

Chosen to cover the five failure modes found in §3 and `CORPUS-NOTES.md`, not
just the five most recent. Each carries a *what a naive summary gets wrong* line
— that line is the regression-catching part and is the most load-bearing content
in this section.

---

### 1. Gazette 2481/22 — 27 March 2026
*Tests: supersession chain, annexure substance, an effective date later overridden*

- **Authority:** Rukdevi Perpetua Himali Fernando, Commissioner General of Inland Revenue
- **Enabling Act:** Value Added Tax Act, No. 14 of 2002, section 20
- **Effective date:** 01 July 2026 **as published — but since amended to 01 October 2026 by `2500/106`**
- **Who it affects:** Every VAT-registered person in Sri Lanka
- **Summary:** Sets a new mandatory format for VAT tax invoices, detailed in Annexure I. The earlier format from `2463/05` becomes optional and is rescinded from the same date. The Annexure specifies invoice serial numbering (`YYMMM_QQQQ_XXXXX`, max 40 characters, no spaces), mandatory supplier and purchaser TINs of nine digits, value stated in LKR without cents, and retention of both copies for five years.
- **Tags:** vat, tax-invoice, compliance, record-keeping, supersedes
- **What a naive summary gets wrong:** states July 2026 as the deadline. It is October. Also easy to miss that this differs from `2463/05` in substance — telephone number became *optional* and the TIN gained a nine-digit specification.

### 2. Gazette 2500/106 — 06 August 2026
*Tests: the metadata-only amendment — trivial-looking, high-consequence*

- **Authority:** Rukdevi Perpetua Himali Fernando, Commissioner General of Inland Revenue
- **Enabling Act:** Value Added Tax Act, No. 14 of 2002, section 20
- **Effective date:** immediate (the *amendment* takes effect on publication; what it changes is the operative date of `2481/22`)
- **Who it affects:** Every VAT-registered person — **nowhere stated in the document**
- **Summary:** Two sentences. Postpones the new mandatory tax invoice format from 01 July 2026 to 01 October 2026. Everything else in `2481/22` is unchanged.
- **Tags:** vat, tax-invoice, deadline-extension, amends
- **What a naive summary gets wrong:** dismisses it as administrative housekeeping. It is the only reason the correct answer today is October. Summarised standalone it is nearly meaningless; its entire value is the edge to `2481/22`.

### 3. Gazette 2363/22 — 19 December 2023
*Tests: audience inference with zero applicability statement; surgical amendment*

- **Authority:** Ranil Wickremesinghe, Minister of Finance, Economic Stabilization and National Policies
- **Enabling Act:** Value Added Tax Act, No. 14 of 2002, section 2A
- **Effective date:** 01 January 2024
- **Who it affects:** Every VAT-registered business and, through prices, every consumer — **the document never says this**
- **Summary:** Raises the standard VAT rate to eighteen per cent on the import and/or supply of goods and services. Technically it substitutes sub-paragraph (b) of paragraph 1 of the order in `2282/26`, and rescinds `2295/08` from the same date.
- **Tags:** vat, rate-change, amends, rescinds
- **What a naive summary gets wrong:** the document reads as a dry textual substitution and never states its own impact. A literal summary — "amends sub-paragraph (b) of paragraph 1" — is accurate and useless. This is the clearest case in the corpus where the affected population must be inferred from the enabling Act.

### 4. Gazette 2334/21 — 31 May 2023
*Tests: two effective dates in one document; substance on page 2*

- **Authority:** Ranil Wickremesinghe, Minister of Finance, Economic Stabilization and National Policies, with the consent of the Commissioner General of Inland Revenue
- **Enabling Act:** Inland Revenue Act, No. 24 of 2017, section 102(3)
- **Effective dates:** **two** — Part A from 01 June 2023; Part B from 01 January 2024
- **Who it affects:** Part A, fourteen listed categories. Part B, **every resident individual aged 18 or over**
- **Summary:** Makes income-tax registration compulsory for additional classes of people. Part A covers registered professionals (doctors, chartered and management accountants, engineers, bankers, architects, quantity surveyors, attorneys), anyone with a business registered at a Divisional Secretariat, vehicle owners other than three-wheelers/motorcycles/hand tractors, anyone who acquired immovable property on or after 01 April 2018, employees whose combined provident fund contributions exceed Rs 20,000 a month, anyone obtaining a building plan approval, and anyone receiving Rs 100,000 a month or Rs 1,200,000 a year for services. Part B then extends registration to every remaining resident individual aged 18 or over. Those already registered under section 102 are excluded.
- **Tags:** income-tax, registration, compulsory, mass-impact
- **What a naive summary gets wrong:** page 1 says only "the classes specified in PART A or PART B of the Schedule" — the entire substance, including "every adult", is on page 2. A page-1 summary conveys nothing. Reporting a single effective date is also wrong; there are two, seven months apart.

### 5. Gazette 2456/02 — 29 September 2025
*Tests: actionable deadlines buried at the end of the document*

- **Authority:** Rukdevi Perpetua Himali Fernando, Commissioner General of Inland Revenue
- **Enabling Act:** Value Added Tax Act, No. 14 of 2002, section 22(5)(f)
- **Effective date:** 01 October 2025
- **Who it affects:** VAT-registered persons claiming refunds on excess input credits — specifically eligible exporters (s.83), suppliers where more than 50% of supplies go to a Strategic Development Project or a Specified Project, and projects approved under s.22(7). Also every Registered Identified Supplier and Purchaser under the outgoing SVAT scheme.
- **Summary:** Replaces the abolished Simplified VAT (SVAT) scheme with a Risk Based Refund Scheme. Claimants are rated low, medium or high risk; low and medium risk receive refunds without pre-verification, high risk only after it. Ratings are reviewed at six-month intervals. Guidelines in `1986/09` are rescinded from the taxable period beginning 01 October 2025. A set of hard transitional deadlines applies: suspended supplies entered on Form SVAT 04 by 15 October 2025, resubmission and Registered Identified Purchaser credit vouchers by 20 October, Schedules SVAT 06 and 07 by 30 October, and unused credit vouchers surrendered to MDC Unit 01 by 10 November 2025.
- **Tags:** vat, refunds, svat-abolition, deadline, rescinds
- **What a naive summary gets wrong:** stops at "SVAT is replaced by a risk-based scheme" and misses every deadline. This document carries 21 date mentions, 13 of them distinct, and the actionable ones sit in the final fifth of the text. It is the strongest evidence that summarising from the opening paragraphs is not viable.

---

**Optional sixth, if you want one more:** `2443/30` (VAT on non-resident digital
services) is the best product demo in the corpus — it names PayPal, Stripe,
OpenSea and Binance, and sets a Rs 60M/12-month registration threshold.

## 7. Open questions — answered

**Does the listing ever change a row in place?** Still unknown; needs a second
observation over time. The `sha256` column in `data/manifest.csv` exists to
answer this on the next fetch. Given how often gazettes amend each other
(above), assume corrections are possible and re-check hashes rather than
trusting append-only.

**Why does 2018 have 23 entries?** Not a different kind of notice — a
legislative burst. **14 of the 23 are dated 01 Apr 2018**, the commencement date
of the Inland Revenue Act, No. 24 of 2017 (`2064/50` through `2064/64`, a
contiguous run of sub-numbers). A new principal Act drops a cluster of
implementing notices on one day.
→ *Consequence:* volume is bursty. A daily poll must handle 15 new gazettes in
one run, not the 3–6/year average. Don't size on the mean.

**Is 2010 really missing?** Yes — genuinely absent from the page, no heading, no
empty section. 2020 has exactly one entry (`2194/50`). Low/zero years are real,
so "no new gazettes" is a normal state the pipeline must not treat as an error.

**Is this listing complete vs documents.gov.lk?** ⚠ **Unverified, and currently
hard to verify.** Every gazette footer points to `www.documents.gov.lk`, but that
host fails TLS (`SSL_ERROR_SYSCALL`), and the apex `documents.gov.lk` now serves
a JS "CMS Admin Dashboard" shell with no server-rendered links.
→ *Consequence:* treat the IRD listing as the single practical source for v0 and
say so honestly. Completeness is an assumption, not a verified fact. Worth
re-checking later — if IRD ever omits a tax gazette that documents.gov.lk
carries, the "we tell you the day it's published" promise breaks silently.

---

## 8. What to look for while reading

The machine survey answered the mechanical questions. These are the ones only a
human read can answer.

**Fields — is it reliably there, or did I get lucky?**
- Is there always an **effective date**, and is it ever absent, retroactive, or
  conditional ("on a date to be appointed")? This is the field the product's
  promise rests on, and it is *not* the publication date.
- Is the **affected population** ever stated explicitly, or must it be inferred?
  Note the actual phrases used: "every registered person", "withholding agents",
  "licensed commercial banks", "non-resident person".
- Is there always an identifiable **enabling Act + section**?
- Obligation vs. information: does this require someone to *do* something by a
  date, or is it just notice?

**Supersession — the highest-value thing to watch**
- Does it amend, rescind or replace something? Is the target always given as a
  gazette number, or sometimes described only in prose ("the Notice published on
  01 April 2018")? Prose references would be much harder to resolve.
- Does it change only *part* of an earlier gazette (like `2500/106` changing one
  date)? Those are the dangerous ones to summarise standalone.

**Where a plausible summary would be wrong**
- Thresholds, rates, percentages, currency amounts, exemption carve-outs — the
  places a fluent-sounding summary can silently invert meaning.
- Anything where the Schedule/Annexure contradicts or narrows the operative
  clause on page 1.

**Extraction reality-check**
- Does the English half always sit in the same structural position?
- Do any tables/forms in Annexures come out of `-layout` as unusable soup?
- Is any substance carried in an image rather than text?

**And the honest one:** after reading, could *you* have written a useful alert
from the first page alone? If not, the pipeline can't summarise from page 1
either.
